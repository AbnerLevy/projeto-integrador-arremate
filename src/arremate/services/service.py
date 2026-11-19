"""Regras de produção e permissões. Toda alteração ocorre dentro de uma transação."""
import hashlib
import hmac
import secrets
import re
from uuid import uuid4
from datetime import datetime, timezone, date
from decimal import Decimal, InvalidOperation

class Error(Exception):
    def __init__(self, message, status=400):
        self.message, self.status = message, status
        super().__init__(message)

def require(ok, message, status=400):
    if not ok:
        raise Error(message, status)

def uid():
    return str(uuid4())

def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def text(value, label, limit=120, optional=False):
    require(isinstance(value, str), f'{label}: informe um texto.')
    value = value.strip()
    require(len(value) <= limit and (optional or value), f'{label}: preencha até {limit} caracteres.')
    return value

def integer(value, low=0, high=1000000):
    require(type(value) is int and low <= value <= high, f'Informe um inteiro entre {low} e {high}.')
    return value

def money(value):
    try:
        amount = Decimal(str(value))
        require(amount.is_finite() and 0 <= amount <= 100000, 'Valor por peça inválido.')
        cents = amount * 100
        require(cents == cents.to_integral_value(), 'Use até duas casas decimais.')
        return int(cents)
    except (InvalidOperation, ValueError):
        raise Error('Valor por peça inválido.')

def valid_date(value, optional=False):
    if optional and not value:
        return ''
    value = text(value, 'Data', 10)
    try:
        require(date.fromisoformat(value).isoformat() == value, 'Data inválida.')
    except ValueError:
        raise Error('Data inválida.')
    return value

def password_hash(password):
    require(isinstance(password, str) and 8 <= len(password) <= 128, 'Use uma senha de 8 a 128 caracteres.')
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600000).hex()
    return f'pbkdf2_sha256$600000${salt}${digest}'

def verify_password(password, encoded):
    try:
        algorithm, rounds, salt, expected = encoded.split('$')
        if algorithm != 'pbkdf2_sha256' or not isinstance(password, str) or len(password) > 128:
            return False
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(rounds)).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False

def add_user(q, name, username, specialty, password, role='worker'):
    username = text(username, 'Login', 40).lower()
    require(re.fullmatch(r'[a-z0-9._-]{3,40}', username), 'Login: use de 3 a 40 letras, números, pontos, traços ou sublinhados.')
    require(not q.one('SELECT id FROM users WHERE username=?', (username,)), 'Este login já está em uso.', 409)
    user_id = uid()
    q.execute('INSERT INTO users(id,name,username,specialty,role,password_hash) VALUES(?,?,?,?,?,?)',
              (user_id, text(name,'Nome',80), username, text(specialty,'Função',80), role, password_hash(password)))
    return user_id

def notify(q, user_id, batch_id, message):
    q.execute('INSERT INTO notices(id,user_id,batch_id,message,created_at) VALUES(?,?,?,?,?)',
              (uid(), user_id, batch_id, message, now()))

def manager(me):
    require(me['role'] == 'manager', 'Ação exclusiva da gerente.', 403)

def assignee(q, value):
    person = q.one("SELECT id FROM users WHERE id=? AND role='worker' AND enabled=1", (text(value,'Responsável'),))
    require(person, 'Selecione uma pessoa com acesso liberado.')
    return person['id']

def view(q, me):
    """A gerente vê tudo. O funcionário recebe só os lotes em que está alocado."""
    is_manager = me['role'] == 'manager'
    user_fields = 'id,name,role,specialty' + (',username,enabled' if is_manager else '')
    members = q.all(f'SELECT {user_fields} FROM users ORDER BY name')
    safe_me = {k: me[k] for k in ('id','name','role','specialty','username')}
    batches = q.all('SELECT * FROM batches ORDER BY created_at DESC,code DESC')
    tasks = q.all('SELECT * FROM tasks ORDER BY position')
    if not is_manager:
        # Filtrar no servidor protege os dados mesmo que alguém altere o JavaScript.
        assigned_batches = set()
        for task in tasks:
            if task['assignee_id'] == me['id']:
                assigned_batches.add(task['batch_id'])
        batches = [batch for batch in batches if batch['id'] in assigned_batches]
        tasks = [task for task in tasks if task['batch_id'] in assigned_batches]
        # Mostrar os responsáveis do caminho do lote, sem a lista inteira da equipe.
        visible_people = {task['assignee_id'] for task in tasks}
        visible_people.add(me['id'])
        members = [member for member in members if member['id'] in visible_people]
    for batch in batches:
        batch['tasks'] = [t for t in tasks if t['batch_id'] == batch['id']]
        batch['remaining'] = batch['tasks'][-1]['outgoing']
        batch['lost'] = batch['quantity'] - batch['remaining']
        batch['finished'] = all(t['status'] in ('done','cancelled') for t in batch['tasks'])
        if not is_manager:
            for key in ('client','price_cents','notes'):
                batch.pop(key, None)
    losses = q.all('SELECT * FROM losses ORDER BY created_at DESC')
    visible_batches = {batch['id'] for batch in batches}
    if not is_manager:
        losses = [loss for loss in losses if loss['actor_id'] == me['id'] and loss['batch_id'] in visible_batches]
    notices = q.all('SELECT * FROM notices WHERE user_id=? ORDER BY created_at DESC LIMIT 100', (me['id'],))
    notices = [notice for notice in notices if notice['batch_id'] in visible_batches]
    return dict(me=safe_me, members=members, batches=batches, losses=losses,
                stages=q.all('SELECT * FROM stages ORDER BY position') if is_manager else [],
                products=q.all('SELECT * FROM products ORDER BY name') if is_manager else [],
                notices=notices,
                revision=q.one('SELECT revision FROM meta WHERE id=1')['revision'])

def apply(q, me, c):
    action = c.get('type')
    if action == 'read-notices':
        q.execute('UPDATE notices SET seen=1 WHERE user_id=?', (me['id'],))
        return
    if action == 'add-member':
        manager(me)
        add_user(q, c.get('name'), c.get('username'), c.get('specialty'), c.get('password'))
        return
    if action in ('toggle-access','reset-password'):
        manager(me)
        person = q.one("SELECT * FROM users WHERE id=? AND role='worker'", (c.get('member_id'),))
        require(person, 'Funcionário não encontrado.',404)
        if action == 'toggle-access':
            q.execute('UPDATE users SET enabled=? WHERE id=?', (1-person['enabled'],person['id']))
        else:
            q.execute('UPDATE users SET password_hash=? WHERE id=?', (password_hash(c.get('password')),person['id']))
        q.execute('DELETE FROM sessions WHERE user_id=?', (person['id'],))
        return
    if action == 'add-product':
        manager(me)
        name = text(c.get('name'), 'Produto',100)
        require(not q.one('SELECT id FROM products WHERE LOWER(name)=LOWER(?)',(name,)), 'Produto já cadastrado.')
        q.execute('INSERT INTO products(id,name,price_cents) VALUES(?,?,?)', (uid(),name,money(c.get('price'))))
        return
    if action in ('add-stage','edit-stage','remove-stage'):
        manager(me)
        if action == 'remove-stage':
            q.execute('DELETE FROM stages WHERE id=?',(c.get('stage_id'),))
        elif action == 'edit-stage':
            require(q.one('SELECT id FROM stages WHERE id=?',(c.get('stage_id'),)), 'Etapa não encontrada.',404)
            q.execute('UPDATE stages SET name=?,sector=? WHERE id=?',
                      (text(c.get('name'),'Etapa',80),text(c.get('sector'),'Setor',80),c['stage_id']))
        else:
            position = q.one('SELECT COALESCE(MAX(position),0)+1 AS n FROM stages')['n']
            q.execute('INSERT INTO stages(id,name,sector,position) VALUES(?,?,?,?)',
                      (uid(),text(c.get('name'),'Etapa',80),text(c.get('sector'),'Setor',80),position))
        return
    if action == 'create-batch':
        manager(me)
        steps = c.get('stages')
        require(isinstance(steps,list) and 1 <= len(steps) <= 30, 'Escolha de 1 a 30 etapas.')
        quantity = integer(c.get('quantity'),1)
        due = valid_date(c.get('due_date'))
        batch_id = uid()
        code_number = q.one('SELECT next_code FROM meta WHERE id=1')['next_code']
        code = f'LT-{code_number:04d}'
        q.execute('UPDATE meta SET next_code=next_code+1 WHERE id=1')
        q.execute('INSERT INTO batches(id,code,product,client,quantity,price_cents,color,sizes,due_date,notes,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                  (batch_id,code,text(c.get('product'),'Produto'),text(c.get('client',''),'Cliente',100,True),quantity,money(c.get('price')),
                   text(c.get('color',''),'Cor',80,True),text(c.get('sizes',''),'Tamanhos',80,True),due,text(c.get('notes',''),'Observações',1000,True),now()))
        previous_date = ''
        for i, step in enumerate(steps):
            require(isinstance(step,dict), 'Etapa inválida.')
            definition = q.one('SELECT * FROM stages WHERE id=?',(step.get('stage_id'),))
            require(definition,'Etapa não cadastrada.')
            person_id = assignee(q,step.get('assignee_id'))
            planned = valid_date(step.get('planned_date',''),True)
            require(not planned or previous_date <= planned <= due, 'Datas das etapas devem estar em ordem e até a entrega.')
            previous_date = planned or previous_date
            q.execute('INSERT INTO tasks(id,batch_id,position,name,sector,assignee_id,planned_date,status,incoming,outgoing) VALUES(?,?,?,?,?,?,?,?,?,?)',
                      (uid(),batch_id,i,definition['name'],definition['sector'],person_id,planned,'waiting' if i else 'ready',quantity,quantity))
            notify(q,person_id,batch_id,f"{code}: nova tarefa — {definition['name']}. " + ('Disponível para iniciar.' if i == 0 else 'Aguarde sua vez.'))
        return
    task = q.one('SELECT * FROM tasks WHERE id=?',(c.get('task_id'),))
    require(task,'Etapa não encontrada.',404)
    batch = q.one('SELECT * FROM batches WHERE id=?',(task['batch_id'],))
    if action == 'assign':
        manager(me)
        require(task['status'] in ('waiting','ready'),'A etapa já foi iniciada.',409)
        person_id = assignee(q,c.get('assignee_id'))
        q.execute('UPDATE tasks SET assignee_id=? WHERE id=?',(person_id,task['id']))
        notify(q,person_id,batch['id'],f"{batch['code']}: você foi atribuído a {task['name']}.")
        return
    # Até a gerente só inicia/conclui tarefas atribuídas a ela.
    require(task['assignee_id'] == me['id'],'Esta etapa pertence a outro funcionário.',403)
    later = q.all('SELECT * FROM tasks WHERE batch_id=? AND position>? ORDER BY position',(batch['id'],task['position']))
    if action == 'start':
        require(task['status']=='ready','Esta etapa ainda não está liberada ou já foi iniciada.',409)
        previous = q.one('SELECT status FROM tasks WHERE batch_id=? AND position=?',(batch['id'],task['position']-1))
        require(not previous or previous['status']=='done','Conclua a etapa anterior primeiro.',409)
        require(task['incoming']>0,'Não há peças disponíveis.')
        q.execute("UPDATE tasks SET status='active',started_at=? WHERE id=?",(now(),task['id']))
    elif action in ('complete','loss'):
        expected = 'active' if action == 'complete' else 'done'
        require(task['status']==expected,'O estado da etapa mudou. Atualize o painel.',409)
        if action == 'complete':
            # A resposta Sim/Não é obrigatória. Não presumir "sem perda".
            had_loss = c.get('had_loss')
            require(type(had_loss) is bool, 'Informe se houve perda antes de finalizar.')
            quantity = integer(c.get('quantity'), 0, task['outgoing'])
            if had_loss:
                require(quantity > 0, 'Informe quantas peças foram perdidas.')
            else:
                require(quantity == 0, 'Sem perda, a quantidade perdida deve ser zero.')
        else:
            quantity = integer(c.get('quantity',0),0,task['outgoing'])
        reason = text(c.get('reason',''),'Observação',600,True)
        require(not quantity or reason,'Descreva o motivo da perda.')
        require(action=='complete' or quantity or reason,'Informe uma perda ou observação.')
        require(all(t['status'] in ('waiting','ready','cancelled') for t in later),
                'A próxima etapa já foi iniciada. Não é possível alterar a quantidade anterior.',409)
        outgoing = task['outgoing'] - quantity
        if quantity or reason:
            q.execute('INSERT INTO losses(id,task_id,batch_id,actor_id,quantity,reason,created_at) VALUES(?,?,?,?,?,?,?)',
                      (uid(),task['id'],batch['id'],me['id'],quantity,reason,now()))
        q.execute('UPDATE tasks SET outgoing=? WHERE id=?',(outgoing,task['id']))
        for step in later:
            q.execute('UPDATE tasks SET incoming=incoming-?,outgoing=outgoing-? WHERE id=?',(quantity,quantity,step['id']))
        if action == 'complete':
            q.execute("UPDATE tasks SET status='done',completed_at=? WHERE id=?",(now(),task['id']))
            if later and outgoing:
                q.execute("UPDATE tasks SET status='ready' WHERE id=?",(later[0]['id'],))
                notify(q,later[0]['assignee_id'],batch['id'],f"{batch['code']}: sua etapa {later[0]['name']} está liberada, com {outgoing} peças.")
        if not outgoing:
            q.execute("UPDATE tasks SET status='cancelled' WHERE batch_id=? AND position>?",(batch['id'],task['position']))
        managers = q.all("SELECT id FROM users WHERE role='manager'")
        if quantity:
            recipients = {t['assignee_id'] for t in later} | {m['id'] for m in managers}
            for person_id in recipients:
                notify(q,person_id,batch['id'],f"{batch['code']}: perda de {quantity} peças em {task['name']}. Restam {outgoing}.")
        if not later or not outgoing:
            for person in managers:
                notify(q,person['id'],batch['id'],f"{batch['code']}: encerrado com {outgoing} peças.")
    else:
        raise Error('Ação desconhecida.')
