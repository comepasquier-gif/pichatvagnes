from __future__ import annotations

import json, os, platform, sys, time, zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List

from config import (APP_VERSION, DATABASE_BACKEND, DATABASE_PATH, PROJECT_ROOT, RUNTIME_DIR,
                    PUBLIC_URL, STORAGE_BACKEND, PICHAT_SECRET_KEY, RENDER_MODE)
from database import get_db_cursor, is_postgres
from services.storage_service import storage_stats

STARTED_AT=time.time(); SUPPORT_DIR=RUNTIME_DIR/'support'

def _iso(ts:float)->str:return datetime.fromtimestamp(ts,timezone.utc).replace(microsecond=0).isoformat()
def _human_size(value:int)->str:
    size=float(max(0,value));units=['o','Ko','Mo','Go','To']
    for unit in units:
        if size<1024 or unit==units[-1]:return ('%.1f %s'%(size,unit)) if unit!='o' else ('%d o'%int(size))
        size/=1024
    return '%d o'%value

def _table_exists(c,name:str)->bool:
    try:c.execute('PRAGMA table_info(%s)'%name);return bool(c.fetchall())
    except Exception:return False

def _count(c,table,where='',params=()):
    if not _table_exists(c,table):return 0
    sql='SELECT COUNT(*) AS n FROM "%s"'%table
    if where:sql+=' WHERE '+where
    r=c.execute(sql,params).fetchone();return int(r['n'] if r else 0)

def _database_integrity()->Dict[str,Any]:
    try:
        with get_db_cursor() as c:
            probe=c.execute('SELECT 1 AS ok').fetchone()
            size=0
            if is_postgres():
                try:size=int(c.execute('SELECT pg_database_size(current_database()) AS n').fetchone()['n'] or 0)
                except Exception:size=0
            else:size=DATABASE_PATH.stat().st_size if DATABASE_PATH.exists() else 0
        return {'ok':bool(probe and probe['ok']==1),'status':'connected','detail':DATABASE_BACKEND,'backend':DATABASE_BACKEND,'size':size,'size_human':_human_size(size)}
    except Exception as exc:return {'ok':False,'status':'error','detail':str(exc)[:180],'backend':DATABASE_BACKEND,'size':0,'size_human':'0 o'}

def _latest_backup()->Dict[str,Any]:
    try:
        with get_db_cursor() as c:
            n=_count(c,'backup_archives')
            row=c.execute('SELECT name,size_bytes,created_at,integrity_status FROM backup_archives ORDER BY created_at DESC LIMIT 1').fetchone() if n else None
        if not row:return {'count':0,'latest':None,'age_hours':None,'size':0,'size_human':'0 o'}
        created=str(row['created_at'] or '').replace(' ','T')
        try:
            dt=datetime.fromisoformat(created.replace('Z','+00:00'))
            if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
            age=round((datetime.now(timezone.utc)-dt.astimezone(timezone.utc)).total_seconds()/3600,1)
        except Exception:age=None
        size=int(row['size_bytes'] or 0)
        return {'count':n,'latest':row['name'],'latest_at':row['created_at'],'age_hours':age,'size':size,'size_human':_human_size(size),'integrity_status':row['integrity_status']}
    except Exception:return {'count':0,'latest':None,'age_hours':None,'size':0,'size_human':'0 o'}

def _api_status():
    try:
        from services.integration_hub_service import public_status
        return public_status()
    except Exception as exc:return {'configured':False,'last_test_status':'error','error':str(exc)[:160]}

def _stats()->Dict[str,Any]:
    now=datetime.now(timezone.utc);today=now.strftime('%Y-%m-%d 00:00:00');minute=(now-timedelta(seconds=60)).strftime('%Y-%m-%d %H:%M:%S');online_cut=(now-timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S')
    data={}
    with get_db_cursor() as c:
        data['users']=_count(c,'users','is_bot=0')
        data['admins']=_count(c,'users','is_admin=1')
        data['moderators']=_count(c,'users','is_moderator=1')
        data['rooms']=_count(c,'rooms')
        data['sessions']=_count(c,'sessions')
        data['online_users']=_count(c,'sessions','last_seen_at>=?',(online_cut,))
        data['messages']=_count(c,'messages');data['private_messages']=_count(c,'private_messages')
        today_room=_count(c,'messages','created_at>=?',(today,));today_dm=_count(c,'private_messages','created_at>=?',(today,))
        last_min=_count(c,'messages','created_at>=?',(minute,))+_count(c,'private_messages','created_at>=?',(minute,))
        data['messages_today']=today_room+today_dm;data['messages_per_second']=round(last_min/60.0,3)
        data['pending_requests']=_count(c,'registration_requests',"status='pending'")
        data['open_reports']=_count(c,'message_reports',"status='open'")
        data['test_accounts']=_count(c,'users','is_test_account=1') if _table_exists(c,'users') else 0
        data['games']=_count(c,'generated_games')
    return data

def _automod():
    try:
        with get_db_cursor() as c:r=c.execute('SELECT enabled FROM automod_settings WHERE id=1').fetchone()
        return {'ok':True,'enabled':bool(r and r['enabled'])}
    except Exception as exc:return {'ok':False,'enabled':False,'error':str(exc)[:120]}

def _frontend_checks():
    required=['frontend/index.html','frontend/admin.html','frontend/setup.html','frontend/service-worker.js','frontend/manifest.webmanifest','backend/main.py','render.yaml','Dockerfile','requirements.txt']
    return [{'name':rel,'ok':(PROJECT_ROOT/rel).exists()} for rel in required]

def _public_status():
    url=(PUBLIC_URL or os.getenv('RENDER_EXTERNAL_URL','')).strip().rstrip('/')
    https=url.startswith('https://')
    return {'url':url,'https':https,'server':True,'provider':'render' if RENDER_MODE else ('custom' if url else 'local')}

def _readiness(stats,db,backup,storage,public,automod,frontend):
    checks=[
        {'id':'database','label':'Base PostgreSQL connectée','ok':db['ok'] and db['backend']=='postgresql','weight':20,'critical':True},
        {'id':'owner','label':'Propriétaire créé','ok':stats['admins']>0,'weight':15,'critical':True},
        {'id':'storage','label':'Stockage persistant','ok':storage['backend'] in {'database','s3'},'weight':15,'critical':True},
        {'id':'https','label':'URL publique HTTPS','ok':public['https'],'weight':15,'critical':True},
        {'id':'backup','label':'Backup récent (<24 h)','ok':backup.get('age_hours') is not None and float(backup['age_hours'])<=24,'weight':15,'critical':False},
        {'id':'secret','label':'Clé serveur définie','ok':bool(PICHAT_SECRET_KEY),'weight':10,'critical':True},
        {'id':'test','label':'Aucun compte Labo','ok':stats.get('test_accounts',0)==0,'weight':5,'critical':False},
        {'id':'files','label':'Fichiers essentiels présents','ok':all(x['ok'] for x in frontend),'weight':5,'critical':True},
    ]
    score=sum(x['weight'] for x in checks if x['ok']);critical=all(x['ok'] for x in checks if x['critical'])
    return {'score':score,'ready':bool(score>=80 and critical),'checks':checks}

def overview()->Dict[str,Any]:
    stats=_stats();db=_database_integrity();backup=_latest_backup();storage=storage_stats();public=_public_status();api=_api_status();automod=_automod();frontend=_frontend_checks();launch=_readiness(stats,db,backup,storage,public,automod,frontend)
    return {
        'version':APP_VERSION,'edition':'FREE ONLINE','uptime_seconds':int(time.time()-STARTED_AT),'started_at':_iso(STARTED_AT),
        'python':platform.python_version(),'platform':'%s %s'%(platform.system(),platform.machine()),'stats':stats,'database':db,
        'storage':{**storage,'uploads':storage['bytes'],'uploads_human':_human_size(storage['bytes']),'backups':backup['size'],'backups_human':backup['size_human'],'free':0,'free_human':'géré par l’hébergeur'},
        'backup':backup,'api':api,'automod':automod,'frontend':frontend,'launch':launch,'public':public,
        'cloud':{'running':public['https'],'public_url':public['url'],'provider':public['provider']},
        'server':{'ok':True,'state':'online','version':APP_VERSION,'uptime_seconds':int(time.time()-STARTED_AT)},
    }

def create_support_bundle()->Path:
    SUPPORT_DIR.mkdir(parents=True,exist_ok=True);payload=overview();stamp=datetime.now().strftime('%Y%m%d-%H%M%S');path=SUPPORT_DIR/f'PiChat_PRO_Diagnostic_{stamp}.zip'
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('diagnostic.json',json.dumps(payload,ensure_ascii=False,indent=2));z.writestr('README.txt','PiChat 3.5 Diagnostic\nAucun mot de passe, token, cookie, clé API ou base n’est inclus.\n')
        if (PROJECT_ROOT/'VERSION.txt').exists():z.write(PROJECT_ROOT/'VERSION.txt','VERSION.txt')
    return path
