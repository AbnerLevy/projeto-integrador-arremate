"""Arremate: servidor WSGI sem framework. Execute python app.py --help."""
import argparse
import getpass
import hashlib
import json
import logging
import os
import secrets
import time
from http.cookies import SimpleCookie
from pathlib import Path
from wsgiref.simple_server import make_server
from db import Database, ROOT
from service import Error, require, add_user, password_hash, verify_password, apply, view, uid, now

DB = Database()
SESSION_AGE = 12 * 60 * 60
DUMMY_HASH = password_hash(secrets.token_urlsafe(20))

def session_token(environ):
    cookie = SimpleCookie()
    try:
        cookie.load(environ.get('HTTP_COOKIE',''))
        raw = cookie['arremate_session'].value if 'arremate_session' in cookie else ''
    except Exception:
        raw = ''
    return hashlib.sha256(raw.encode()).hexdigest()

def session_user(q, environ):
    session = q.one('SELECT * FROM sessions WHERE token_hash=? AND expires>?',
                    (session_token(environ),int(time.time())))
    require(session,'Entre com seu login e senha.',401)
    me = q.one('SELECT * FROM users WHERE id=? AND enabled=1',(session['user_id'],))
    require(me,'Seu acesso foi bloqueado. Procure a gerente.',401)
    return session, me

def cookie(value, clear=False):
    secure = '; Secure' if os.getenv('COOKIE_SECURE','0')=='1' else ''
    return ('Set-Cookie',f'arremate_session={value}; Path=/; HttpOnly; SameSite=Strict; Max-Age={0 if clear else SESSION_AGE}{secure}')

def read_json(environ):
    require(environ.get('HTTP_X_ARREMATE_REQUEST')=='1','Requisição não autorizada.',403)
    require(environ.get('CONTENT_TYPE','').split(';')[0]=='application/json','Envie JSON.',415)
    try:
        length = int(environ.get('CONTENT_LENGTH') or 0)
    except ValueError:
        raise Error('Tamanho inválido.')
    require(0 < length <= 100000,'Requisição vazia ou grande demais.',413)
    try:
        data = json.loads(environ['wsgi.input'].read(length))
    except (ValueError, UnicodeError):
        raise Error('JSON inválido.')
    require(isinstance(data,dict),'Envie um objeto JSON.')
    return data

def login(environ, data):
    username = data.get('username','')
    password = data.get('password','')
    require(isinstance(username,str) and isinstance(password,str) and len(username)<=40 and len(password)<=128,'Login ou senha inválidos.',401)
    username = username.strip().lower()
    # O endereço é o do socket, nunca um cabeçalho X-Forwarded-For não confiável.
    key = hashlib.sha256(environ.get('REMOTE_ADDR','local').encode()).hexdigest()
    timestamp = int(time.time())
    result = None
    with DB.transaction(write=True) as q:
        q.execute('DELETE FROM login_limits WHERE reset_at<=?',(timestamp,))
        q.execute('DELETE FROM sessions WHERE expires<=?',(timestamp,))
        limit = q.one('SELECT * FROM login_limits WHERE key=?',(key,))
        require(not limit or limit['attempts']<20,'Muitas tentativas. Aguarde 15 minutos.',429)
        person = q.one('SELECT * FROM users WHERE username=?',(username,))
        valid = verify_password(password,person['password_hash'] if person else DUMMY_HASH)
        if person and person['enabled'] and valid:
            q.execute('DELETE FROM login_limits WHERE key=?',(key,))
            raw, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            q.execute('DELETE FROM sessions WHERE token_hash=?',(session_token(environ),))
            q.execute('INSERT INTO sessions(token_hash,user_id,csrf,expires) VALUES(?,?,?,?)',
                      (hashlib.sha256(raw.encode()).hexdigest(),person['id'],csrf,timestamp+SESSION_AGE))
            result = ({'ok':True},[cookie(raw)])
        else:
            q.execute('INSERT INTO login_limits(key,attempts,reset_at) VALUES(?,1,?) ON CONFLICT(key) DO UPDATE SET attempts=login_limits.attempts+1',
                      (key,timestamp+900))
    require(result,'Login ou senha inválidos.',401)
    return result

def route(environ):
    path, method = environ.get('PATH_INFO','/'), environ['REQUEST_METHOD']
    if method=='GET' and path=='/api/state':
        with DB.transaction() as q:
            session, me = session_user(q,environ)
            data = view(q,me)
            data['csrf'] = session['csrf']
            return data, []
    require(method=='POST' and path in ('/api/login','/api/logout','/api/command'),'Página não encontrada.',404)
    data = read_json(environ)
    if path=='/api/login':
        return login(environ,data)
    with DB.transaction(write=True) as q:
        session, me = session_user(q,environ)
        require(secrets.compare_digest(environ.get('HTTP_X_CSRF_TOKEN',''),session['csrf']),'Sessão inválida. Atualize a página.',403)
        if path=='/api/logout':
            q.execute('DELETE FROM sessions WHERE token_hash=?',(session['token_hash'],))
            return {'ok':True}, [cookie('',True)]
        request_id = data.get('request_id')
        require(isinstance(request_id,str) and 16 <= len(request_id) <= 80,'Identificador de operação inválido.')
        digest = hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
        old = q.one('SELECT * FROM commands WHERE id=?',(request_id,))
        if old:
            require(old['actor_id']==me['id'] and old['payload_hash']==digest,'Operação duplicada com conteúdo diferente.',409)
        else:
            apply(q,me,data)
            q.execute('INSERT INTO commands(id,actor_id,payload_hash,created_at) VALUES(?,?,?,?)',(request_id,me['id'],digest,now()))
            q.execute('UPDATE meta SET revision=revision+1 WHERE id=1')
        result = view(q,me)
        result['csrf'] = session['csrf']
        return result, []

STATIC = {'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),
          '/style.css':('style.css','text/css; charset=utf-8'),'/favicon.svg':('favicon.svg','image/svg+xml')}

def application(environ, start_response):
    headers = [('Cache-Control','no-store'),('X-Content-Type-Options','nosniff'),('Referrer-Policy','same-origin'),
               ('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")]
    status = 200
    path = environ.get('PATH_INFO','/')
    try:
        if environ['REQUEST_METHOD']=='GET' and path in STATIC:
            filename, content_type = STATIC[path]
            body = (ROOT / 'static' / filename).read_bytes()
        else:
            data, extra_headers = route(environ)
            headers.extend(extra_headers)
            body = json.dumps(data,ensure_ascii=False).encode()
            content_type = 'application/json; charset=utf-8'
    except Error as error:
        status, content_type = error.status,'application/json; charset=utf-8'
        body = json.dumps({'error':error.message},ensure_ascii=False).encode()
    except Exception:
        # Não registrar SQL, senhas ou strings de conexão em respostas/logs públicos.
        logging.error('Falha interna em %s. Verifique inicialização e conexão do banco.', path)
        status, content_type = 500,'application/json; charset=utf-8'
        body = json.dumps({'error':'Falha ao acessar o banco. Verifique a configuração do servidor.'}).encode()
    labels = {200:'OK',400:'Bad Request',401:'Unauthorized',403:'Forbidden',404:'Not Found',409:'Conflict',413:'Payload Too Large',415:'Unsupported Media Type',429:'Too Many Requests',500:'Internal Server Error'}
    headers.extend([('Content-Type',content_type),('Content-Length',str(len(body)))])
    start_response(f'{status} {labels.get(status,"Error")}',headers)
    return [body]

def initialize():
    DB.initialize()
    with DB.transaction() as q:
        exists = q.one("SELECT id FROM users WHERE role='manager'")
    if exists:
        print('Banco pronto. O acesso da gerente existente foi preservado.')
        return
    print('Crie o primeiro acesso da gerente (a senha não aparece ao digitar).')
    name = input('Nome: ')
    username = input('Login: ')
    password = getpass.getpass('Senha (mínimo 8 caracteres): ')
    require(password==getpass.getpass('Repita a senha: '),'As senhas não coincidem.')
    with DB.transaction(write=True) as q:
        require(not q.one("SELECT id FROM users WHERE role='manager'"),'Outra gerente já inicializou este banco.')
        add_user(q,name,username,'Gestão da produção',password,'manager')
        defaults = [('Corte','Corte'),('Cós','Costura'),('Passantes','Costura'),('Travetes','Costura'),('Caseados','Costura'),('Acabamento','Acabamento'),('Limpeza de fios','Acabamento')]
        for i,(stage,sector) in enumerate(defaults):
            q.execute('INSERT INTO stages(id,name,sector,position) VALUES(?,?,?,?)',(uid(),stage,sector,i))
    print('Banco e gerente criados. Execute: python app.py')

def main():
    parser = argparse.ArgumentParser(description='Arremate — HTML, CSS, JavaScript e Python sem frameworks.')
    parser.add_argument('command',nargs='?',choices=['serve','init','backup','reset-password'],default='serve')
    parser.add_argument('--host',default=os.getenv('HOST','127.0.0.1'))
    parser.add_argument('--port',type=int,default=int(os.getenv('PORT','8000')))
    parser.add_argument('--output',help='Destino do backup SQLite')
    args = parser.parse_args()
    try:
        if args.command=='init':
            initialize()
        elif args.command=='backup':
            require(not DB.postgres,'Para PostgreSQL use pg_dump conforme o README.')
            require(DB.path.exists(),'Banco não encontrado.')
            import sqlite3
            path = Path(args.output or f'backup-arremate-{int(time.time())}.db')
            require(not path.exists(),'O destino já existe. Escolha outro arquivo.')
            with DB.connect() as source, sqlite3.connect(path) as target:
                source.backup(target)
            print(f'Backup salvo em {path.resolve()}')
        elif args.command=='reset-password':
            username = input('Login a recuperar: ').strip().lower()
            password = getpass.getpass('Nova senha: ')
            require(password==getpass.getpass('Repita a senha: '),'As senhas não coincidem.')
            with DB.transaction(write=True) as q:
                user = q.one('SELECT id FROM users WHERE username=?',(username,))
                require(user,'Login não encontrado.')
                q.execute('UPDATE users SET password_hash=? WHERE id=?',(password_hash(password),user['id']))
                q.execute('DELETE FROM sessions WHERE user_id=?',(user['id'],))
            print('Senha alterada; sessões anteriores encerradas.')
        else:
            with DB.transaction() as q:
                require(q.one("SELECT id FROM users WHERE role='manager'"),'Execute python app.py init primeiro.')
            print(f'Arremate em http://{args.host}:{args.port} — Ctrl+C para parar. Servidor de desenvolvimento.')
            with make_server(args.host,args.port,application) as server:
                server.serve_forever()
    except Error as error:
        parser.exit(1,error.message+'\n')
    except KeyboardInterrupt:
        print('\nServidor encerrado.')

if __name__=='__main__':
    main()
