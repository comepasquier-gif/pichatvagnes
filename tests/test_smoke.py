from __future__ import annotations
import io, json, os, tempfile, zipfile
from pathlib import Path

# IMPORTANT: définir l'environnement avant d'importer PiChat.
ROOT=Path(__file__).resolve().parents[1]
DATA=Path(tempfile.mkdtemp(prefix='pichat35-test-'))
os.environ.setdefault('PICHAT_DATA_ROOT',str(DATA))
os.environ.setdefault('PICHAT_SETUP_MODE','1')
os.environ.setdefault('PICHAT_SECRET_KEY','test-only-secret-not-for-production-123456789')
os.environ.setdefault('PICHAT_STORAGE_BACKEND','database')

import sys
sys.path[:0]=[str(ROOT/'backend'),str(ROOT)]
from fastapi.testclient import TestClient
from main import app
from database import get_db_cursor


def run():
    with TestClient(app) as client:
        health=client.get('/api/health');assert health.status_code==200
        assert health.json()['performance']['target_ping_ms']==50
        ping=client.get('/api/ping');assert ping.status_code==200 and ping.json()['target_ms']==50 and ping.json()['version']=='3.5.0'
        login_page=client.get('/login');assert login_page.status_code==200 and 'PiChat 3.5 PERFORMANCE' in login_page.text
        bundle=client.get('/js/chat35.bundle.js?v=3500');assert bundle.status_code==200 and 'immutable' in bundle.headers.get('cache-control','')
        assert client.get('/api/admin/pro').status_code in (401,403)
        st=client.get('/api/setup/status').json();assert st['enabled'] is True
        setup={
            'username':'owner','password':'MotDePasse-Test-34!','instance_name':'PiChat Test',
            'security_level':'strict','registration_mode':'approval','api_key':'','ai_model':'gpt-5.6','setup_key':''
        }
        r=client.post('/api/setup/complete',json=setup);assert r.status_code==200,r.text
        assert client.post('/api/setup/complete',json=setup).status_code==409
        assert client.get('/setup',follow_redirects=False).status_code==303
        login=client.post('/api/login',json={'username':'owner','password':'MotDePasse-Test-34!'});assert login.status_code==200,login.text
        with client.websocket_connect('/ws') as ws:
            ws.send_json({'type':'ping','client_ts':123,'nonce':'smoke35'})
            pong=None
            for _ in range(4):
                event=ws.receive_json()
                if event.get('type')=='pong': pong=event;break
            assert pong and pong['nonce']=='smoke35' and pong['client_ts']==123
        # Dashboard et permissions admin
        pro=client.get('/api/admin/pro');assert pro.status_code==200,pro.text
        data=pro.json();assert data['version']=='3.5.0' and 'messages_per_second' in data['stats']
        # Coffre API : une clé peut être stockée, mais jamais ressortie en clair.
        fake_key='test-secret-api-key-1234567890'
        integ=client.post('/api/admin/integrations',json={'name':'OpenAI test','provider':'openai','api_key':fake_key,'model':'gpt-test'});assert integ.status_code==201,integ.text
        assert fake_key not in integ.text and 'key_hint' in integ.json()
        # PiGame import + sandbox + API limitée
        package={'pichat_game':1,'title':'Test Runner','description':'jeu test','icon':'🎮',
                 'html':'<main><button id="replay">Rejouer</button></main>',
                 'css':'button{padding:12px}',
                 'javascript':"document.getElementById('replay').addEventListener('click',()=>PiGame.submitScore(42));"}
        files={'file':('test.json',json.dumps(package).encode(),'application/json')}
        imp=client.post('/api/game-studio/import-file',files=files);assert imp.status_code==200,imp.text
        game=imp.json();gid=game['id']
        detail=client.get(f'/api/game-studio/games/{gid}');assert detail.status_code==200
        doc=detail.json()['document'];assert "connect-src 'none'" in doc and "Object.defineProperty(window,'PiGame'" in doc and 'allow-same-origin' not in doc
        score=client.post(f'/api/game-studio/games/{gid}/pigame/score',json={'score':42});assert score.status_code==200,score.text
        ach=client.post(f'/api/game-studio/games/{gid}/pigame/achievement',json={'key':'first','title':'Premier'});assert ach.status_code==200
        # Import JS/CSS conservé en 3.5
        js=client.post('/api/game-studio/import-file',files={'file':('game.js',b"document.getElementById('replay')?.addEventListener('click',()=>{});",'application/javascript')});assert js.status_code==200,js.text
        css=client.post('/api/game-studio/import-file',files={'file':('game.css',b"button{border-radius:12px}",'text/css')});assert css.status_code==200,css.text
        html=client.post('/api/game-studio/import-file',files={'file':('game.html',b'<main><button id="replay">Rejouer</button></main><script>document.getElementById("replay").addEventListener("click",()=>{});</script>','text/html')});assert html.status_code==200,html.text
        template=client.get('/api/game-studio/template');assert template.status_code==200
        zipimp=client.post('/api/game-studio/import-file',files={'file':('game.zip',template.content,'application/zip')});assert zipimp.status_code==200,zipimp.text
        # Une tentative dangereuse doit être bloquée.
        bad=dict(package);bad['title']='Bad';bad['javascript']='eval("2+2")'
        badr=client.post('/api/game-studio/import-file',files={'file':('bad.json',json.dumps(bad).encode(),'application/json')});assert badr.status_code==422
        # Labo : comptes identifiés, activité et simulation de plusieurs connexions.
        lab=client.post('/api/admin/test-lab/batches',json={'account_count':4,'prefix':'smoke','password':'PiChatTest2026!','sample_data':True,'include_staff':True});assert lab.status_code==200,lab.text
        # Permissions : un modérateur de test ne devient jamais admin.
        mod_user=lab.json()['credentials'][0]['username']
        modlogin=client.post('/api/login',json={'username':mod_user,'password':'PiChatTest2026!'});assert modlogin.status_code==200,modlogin.text
        assert client.get('/api/admin/pro').status_code in (401,403)
        ownerlogin=client.post('/api/login',json={'username':'owner','password':'MotDePasse-Test-34!'});assert ownerlogin.status_code==200
        sim=client.post('/api/admin/test-lab/simulate-connections',json={'count':8});assert sim.status_code==200,sim.text
        assert sim.json()['simulated_connections']==8
        # Backup portable + édition de fichiers compatible 3.5.
        bk=client.post('/api/admin/pro/backup');assert bk.status_code==200,bk.text
        name=bk.json()['name']
        raw=client.get(f'/api/admin/backups/{name}/download');assert raw.status_code==200
        assert fake_key.encode() not in raw.content
        with zipfile.ZipFile(io.BytesIO(raw.content)) as z:
            export=json.loads(z.read('database/export.json'))
        assert all(not x.get('encrypted_api_key') for x in export['tables'].get('api_integrations',[]))
        assert 'sessions' not in export['tables'] and 'login_attempts' not in export['tables']
        added=client.post(f'/api/admin/backups/{name}/files',files={'file':('note.txt',b'backup smoke file','text/plain')});assert added.status_code==200,added.text
        info=client.get(f'/api/admin/backups/{name}');assert info.status_code==200,info.text
        f=next(x for x in info.json()['files'] if x.get('name')=='note.txt')
        member=f['path'].removeprefix('uploads/')
        extracted=client.get(f'/api/admin/backups/{name}/files/{member}');assert extracted.status_code==200 and extracted.content==b'backup smoke file'
        removed=client.request('DELETE',f'/api/admin/backups/{name}/files',json={'path':f['path']});assert removed.status_code==200,removed.text
        clean=client.delete('/api/admin/test-lab/batches');assert clean.status_code==200,clean.text
        with get_db_cursor() as c:
            versions=[r['version'] for r in c.execute('SELECT version FROM schema_migrations ORDER BY version').fetchall()]
        assert versions==['340001','340002','340003','350001']
        print('SMOKE_OK',{'migrations':versions,'game_id':gid,'score':score.json()['score'],'launch_score':data['launch']['score']})

if __name__=='__main__': run()
