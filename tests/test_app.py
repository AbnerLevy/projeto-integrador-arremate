"""API real WSGI, SQLite/PostgreSQL e concorrência. Sem dependência de testes."""
import io, json, os, tempfile, unittest, hashlib, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import app
from db import Database
from service import add_user, uid

class ArremateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=Database(os.getenv('TEST_DATABASE_URL',''))
        if self.db.postgres:
            # TEST_DATABASE_URL deve apontar SOMENTE para banco descartável!
            with self.db.connect() as conn: conn.execute('DROP SCHEMA IF EXISTS arremate CASCADE')
        else: self.db.path=Path(self.temp.name)/'test.db'
        self.db.initialize(); app.DB=self.db
        with self.db.transaction(write=True) as q:
            self.m=add_user(q,'Gerente','gerente','Gestão','senha-teste-123','manager')
            self.a=add_user(q,'Ana','ana','Corte','senha-teste-123')
            self.b=add_user(q,'Bia','bia','Acabamento','senha-teste-123')
            self.stage=uid()
            q.execute('INSERT INTO stages(id,name,sector,position) VALUES(?,?,?,?)',(self.stage,'Corte','Corte',0))
        self.manager=self.login('gerente');self.ana=self.login('ana');self.bia=self.login('bia')
    def tearDown(self): self.temp.cleanup()
    def request(self,path,body=None,auth=None,csrf=True,custom=True):
        raw=json.dumps(body).encode() if body is not None else b''
        env={'REQUEST_METHOD':'POST' if body is not None else 'GET','PATH_INFO':path,'wsgi.input':io.BytesIO(raw),
             'CONTENT_LENGTH':str(len(raw)),'CONTENT_TYPE':'application/json','REMOTE_ADDR':'127.0.0.1'}
        if custom: env['HTTP_X_ARREMATE_REQUEST']='1'
        if auth:
            env['HTTP_COOKIE']=auth['cookie']
            if csrf: env['HTTP_X_CSRF_TOKEN']=auth['csrf']
        result={}
        def start(status,headers):result.update(status=int(status.split()[0]),headers=dict(headers))
        response=b''.join(app.application(env,start))
        result['data']=json.loads(response) if path.startswith('/api/') else response
        return result
    def login(self,name):
        r=self.request('/api/login',{'username':name,'password':'senha-teste-123'})
        self.assertEqual(r['status'],200,r)
        auth={'cookie':r['headers']['Set-Cookie'].split(';')[0],'csrf':''}
        auth['csrf']=self.request('/api/state',auth=auth)['data']['csrf'];return auth
    def command(self,auth,**data):
        data.setdefault('request_id',uid());return self.request('/api/command',data,auth)
    def batch(self):
        r=self.command(self.manager,type='create-batch',product='Calça',price='4.50',quantity=10,due_date='2027-01-10',
                       stages=[{'stage_id':self.stage,'assignee_id':self.a,'planned_date':'2027-01-08'},
                               {'stage_id':self.stage,'assignee_id':self.b,'planned_date':'2027-01-09'}])
        self.assertEqual(r['status'],200,r);return r['data']['batches'][0]
    def test_manager_cannot_be_assigned_to_stage(self):
        state=self.request('/api/state',auth=self.manager)['data']
        self.assertNotIn(self.m,{person['id'] for person in state['members'] if person['role']=='worker'})
        result=self.command(self.manager,type='create-batch',product='Calça',price='4.50',quantity=10,due_date='2027-01-10',
                            stages=[{'stage_id':self.stage,'assignee_id':self.m}])
        self.assertEqual(result['status'],400,result)
        self.assertEqual(self.request('/api/state',auth=self.manager)['data']['batches'],[])
    def test_flow_permissions_losses_privacy(self):
        batch=self.batch(); first,second=batch['tasks']
        self.assertEqual(self.command(self.bia,type='start',task_id=second['id'])['status'],409)
        self.assertEqual(self.command(self.bia,type='start',task_id=first['id'])['status'],403)
        self.assertEqual(self.command(self.ana,type='add-product',name='X',price='2')['status'],403)
        self.assertEqual(self.command(self.ana,type='start',task_id=first['id'])['status'],200)
        r=self.command(self.ana,type='complete',task_id=first['id'],had_loss=True,quantity=2,reason='Tecido defeituoso')
        self.assertEqual(r['status'],200,r);current=r['data']['batches'][0]
        self.assertEqual(current['tasks'][1]['incoming'],8);self.assertEqual(current['tasks'][1]['status'],'ready')
        self.assertEqual(current['price_cents'],450)
        self.assertNotIn('client',current);self.assertNotIn('notes',current)
        self.assertNotIn('password_hash',json.dumps(r['data']))
        self.assertNotIn('username',r['data']['members'][0]);self.assertTrue(all(n['user_id']==self.a for n in r['data']['notices']))
        self.command(self.bia,type='start',task_id=second['id'])
        self.assertEqual(self.command(self.ana,type='loss',task_id=first['id'],quantity=1,reason='Tarde')['status'],409)
        self.command(self.bia,type='complete',task_id=second['id'],had_loss=True,quantity=1,reason='Costura')
        b=self.request('/api/state',auth=self.manager)['data']['batches'][0]
        self.assertEqual((b['remaining'],b['lost'],b['finished']),(7,3,True));self.assertEqual(b['remaining']*b['price_cents'],3150)
    def test_total_loss_and_notes(self):
        task=self.batch()['tasks'][0]['id'];self.command(self.ana,type='start',task_id=task)
        r=self.command(self.ana,type='complete',task_id=task,had_loss=True,quantity=10,reason='Danificado')
        self.assertEqual(r['data']['batches'][0]['tasks'][1]['status'],'cancelled')
        self.assertTrue(r['data']['batches'][0]['finished'])
        self.assertEqual(self.command(self.ana,type='loss',task_id=task,quantity=0,reason='Conferido')['status'],200)
    def test_rollback_idempotency_validation(self):
        r=self.command(self.manager,type='create-batch',product='X',price='1.005',quantity=10,due_date='2027-01-10',stages=[{'stage_id':self.stage,'assignee_id':self.a}])
        self.assertEqual(r['status'],400);self.assertEqual(self.request('/api/state',auth=self.manager)['data']['batches'],[])
        task=self.batch()['tasks'][0]['id'];self.command(self.ana,type='start',task_id=task)
        data=dict(type='complete',task_id=task,had_loss=True,quantity=2,reason='Perda',request_id=uid())
        self.assertEqual(self.command(self.ana,**data)['status'],200)
        self.assertEqual(self.command(self.ana,**data)['data']['batches'][0]['lost'],2)
        self.assertEqual(self.command(self.ana,**dict(data,quantity=3))['status'],409)
        for quantity in [-1,1.5,9]: self.assertEqual(self.command(self.ana,type='loss',task_id=task,quantity=quantity,reason='X')['status'],400)
    def test_csrf_block_reset_logout(self):
        self.assertEqual(self.request('/api/state')['status'],401)
        self.assertEqual(self.request('/api/command',{'type':'read-notices','request_id':uid()},self.ana,csrf=False)['status'],403)
        self.assertEqual(self.request('/api/login',{'username':'ana','password':'senha-teste-123'},custom=False)['status'],403)
        self.command(self.manager,type='toggle-access',member_id=self.a)
        self.assertEqual(self.request('/api/state',auth=self.ana)['status'],401)
        self.command(self.manager,type='toggle-access',member_id=self.a)
        self.assertEqual(self.request('/api/state',auth=self.ana)['status'],401)
        auth=self.login('ana');self.command(self.manager,type='reset-password',member_id=self.a,password='nova-senha-321')
        self.assertEqual(self.request('/api/state',auth=auth)['status'],401)
        self.assertEqual(self.request('/api/login',{'username':'ana','password':'senha-teste-123'})['status'],401)
        self.assertEqual(self.request('/api/login',{'username':'ana','password':'nova-senha-321'})['status'],200)
        self.request('/api/logout',{},self.bia);self.assertEqual(self.request('/api/state',auth=self.bia)['status'],401)
    def test_concurrent_loss_start(self):
        first,second=self.batch()['tasks'];self.command(self.ana,type='start',task_id=first['id'])
        self.command(self.ana,type='complete',task_id=first['id'],had_loss=False,quantity=0,reason='')
        with ThreadPoolExecutor(max_workers=2) as pool:
            loss=pool.submit(self.command,self.ana,type='loss',task_id=first['id'],quantity=2,reason='Perda')
            start=pool.submit(self.command,self.bia,type='start',task_id=second['id'])
            lr,sr=loss.result(),start.result()
        self.assertEqual(sr['status'],200);self.assertIn(lr['status'],(200,409))
        b=self.request('/api/state',auth=self.manager)['data']['batches'][0]
        self.assertEqual(b['tasks'][1]['incoming'],8 if lr['status']==200 else 10)
    def test_catalog_visibility_rate_limit(self):
        self.batch();self.command(self.manager,type='add-member',name='Caio',username='caio',specialty='Bordado',password='senha-teste-123')
        caio=self.login('caio');state=self.request('/api/state',auth=caio)['data']
        self.assertEqual(len(state['batches']),0);self.assertEqual(state['notices'],[])
        self.assertEqual(self.command(self.manager,type='add-member',name='X',username='caio',specialty='X',password='senha-teste-123')['status'],409)
        self.assertEqual(self.command(self.manager,type='edit-stage',stage_id=self.stage,name='Novo',sector='Preparação')['status'],200)
        self.assertEqual(self.request('/api/state',auth=self.manager)['data']['batches'][0]['tasks'][0]['name'],'Corte')
        with self.db.transaction(write=True) as q:q.execute('INSERT INTO login_limits(key,attempts,reset_at) VALUES(?,?,?)',(hashlib.sha256(b'127.0.0.1').hexdigest(),20,int(time.time())+900))
        self.assertEqual(self.request('/api/login',{'username':'ana','password':'errada'})['status'],429)

    def test_completion_requires_explicit_loss_answer(self):
        first, second = self.batch()['tasks']
        self.command(self.ana, type='start', task_id=first['id'])
        invalid_answers = [
            {}, {'quantity': 0}, {'had_loss': 'false', 'quantity': 0},
            {'had_loss': False}, {'had_loss': False, 'quantity': 1},
            {'had_loss': True, 'quantity': 0, 'reason': 'X'},
            {'had_loss': True, 'quantity': 1, 'reason': ''},
            {'had_loss': True, 'quantity': 11, 'reason': 'X'},
        ]
        for answer in invalid_answers:
            response = self.command(self.ana, type='complete', task_id=first['id'], **answer)
            self.assertEqual(response['status'], 400, response)
            current = self.request('/api/state', auth=self.manager)['data']['batches'][0]
            self.assertEqual(current['tasks'][0]['status'], 'active')
            self.assertEqual(current['tasks'][1]['status'], 'waiting')
            self.assertEqual(current['lost'], 0)
        response = self.command(self.ana, type='complete', task_id=first['id'], had_loss=False, quantity=0, reason='')
        self.assertEqual(response['status'], 200, response)
        self.assertEqual(response['data']['batches'][0]['tasks'][1]['incoming'], 10)
        self.assertEqual(response['data']['batches'][0]['tasks'][1]['status'], 'ready')

    def test_assignment_controls_visibility_and_notices(self):
        batch = self.batch()
        first, second = batch['tasks']
        self.command(self.manager, type='add-member', name='Caio', username='caio', specialty='Bordado', password='senha-teste-123')
        caio = self.login('caio')
        caio_id = self.request('/api/state', auth=caio)['data']['me']['id']
        self.assertEqual(self.request('/api/state', auth=caio)['data']['batches'], [])
        self.assertEqual(self.command(caio, type='start', task_id=first['id'])['status'], 403)
        self.command(self.manager, type='assign', task_id=second['id'], assignee_id=caio_id)
        caio_view = self.request('/api/state', auth=caio)['data']
        self.assertEqual(len(caio_view['batches']), 1)
        self.assertEqual(len(caio_view['batches'][0]['tasks']), 2)
        self.assertTrue(caio_view['notices'])
        self.assertEqual(self.command(caio, type='start', task_id=second['id'])['status'], 409)
        bia_view = self.request('/api/state', auth=self.bia)['data']
        self.assertEqual(bia_view['batches'], [])
        self.assertEqual(bia_view['notices'], [])
        self.assertEqual(len(self.request('/api/state', auth=self.manager)['data']['batches']), 1)

    def test_static_html_contains_forms_and_templates(self):
        response = self.request('/')
        self.assertEqual(response['status'], 200)
        html = response['data'].decode()
        for name in ['tela-login', 'tela-lotes', 'tela-equipe', 'tela-cadastros', 'tela-resultados', 'form-lote', 'form-finalizar', 'houve-perda', 'modelo-lote', 'modelo-etapa-detalhe']:
            self.assertIn('id="' + name + '"', html)
        self.assertIn('Arremate', html)
        javascript = self.request('/app.js')['data'].decode()
        self.assertNotIn('innerHTML', javascript)
        self.assertNotIn('insertAdjacentHTML', javascript)

if __name__=='__main__':unittest.main()
