from __future__ import annotations
import asyncio, json, os, re, secrets
from pathlib import Path
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError
from database import get_db_cursor
from config import PROJECT_ROOT
from services.integration_hub_service import get_openai_api_key
from security import hash_password
from services.message_service import save_message, get_room_history

ENV_PATH=PROJECT_ROOT/'.env'

class AIError(Exception): pass

def _env_key():
    return get_openai_api_key()

def key_configured(): return bool(_env_key())

def ensure_ai_user():
    with get_db_cursor() as c:
        c.execute("SELECT id FROM users WHERE username='PiAI'"); row=c.fetchone()
        if row: return row['id']
        c.execute("INSERT INTO users (username,password_hash,is_bot,status_message) VALUES (?,?,1,?)",('PiAI',hash_password(secrets.token_urlsafe(32)),'IA intégrée PiChat'))
        return c.lastrowid

def get_ai_settings():
    with get_db_cursor() as c:
        c.execute("SELECT enabled,provider,model,trigger_name,instructions,updated_at FROM ai_settings WHERE id=1"); row=c.fetchone()
    d=dict(row) if row else {'enabled':1,'provider':'local','model':'gpt-5.6','trigger_name':'PiAI','instructions':'Tu es PiAI.'}
    d['enabled']=bool(d['enabled']); d['api_key_configured']=key_configured(); return d

def update_ai_settings(enabled,provider,model,trigger_name,instructions):
    provider=(provider or 'local').strip().lower()
    if provider not in {'local','openai'}: raise AIError('Fournisseur IA invalide.')
    trigger=re.sub(r'[^A-Za-z0-9_-]','',trigger_name.strip())[:24] or 'PiAI'
    with get_db_cursor() as c:
        c.execute("UPDATE ai_settings SET enabled=?,provider=?,model=?,trigger_name=?,instructions=?,updated_at=datetime('now') WHERE id=1",(1 if enabled else 0,provider,model.strip()[:80] or 'gpt-5.6',trigger,instructions.strip()[:3000]))
    return get_ai_settings()

def _extract_query(content, trigger):
    m=re.search(r'@'+re.escape(trigger)+r'\b',content,re.I)
    if not m: return None
    q=(content[:m.start()]+content[m.end():]).strip()
    return q or 'Bonjour ! Présente-toi brièvement.'

def _local_answer(query,sender,room_id):
    q=query.lower()
    if any(x in q for x in ['bonjour','salut','hello']): return f"Salut {sender['username']} 👋 Je suis PiAI. Configure OpenAI dans l'admin pour activer mon mode IA complet."
    if 'aide' in q or 'help' in q: return "Je peux répondre avec @PiAI. En mode local, je donne surtout de l'aide PiChat. Un admin peut activer le mode OpenAI dans Administration → IA."
    if 'grade' in q or 'rôle' in q or 'role' in q: return "Les grades sont JOUEUR, MODO de classe et ADMIN. Un MODO reste limité à sa classe."
    return "PiAI est actif en mode local. Pour des réponses génératives, un admin doit configurer une clé OpenAI puis sélectionner le fournisseur OpenAI."

def _openai_sync(query,sender,room_id,settings):
    key=_env_key()
    if not key: raise AIError("Aucune clé OpenAI configurée. Lance CONFIGURER_IA.bat.")
    history=get_room_history(room_id,limit=10)
    context='\n'.join([f"{m['username']}: {m['content']}" for m in history[-8:] if not m.get('is_bot')])
    instructions=(settings['instructions']+"\nContexte PiChat: l'utilisateur est "+sender['username']+", classe "+str(sender.get('class_code') or '-')+". Ne prétends pas avoir des permissions d'administration. Réponds dans le salon, sans Markdown excessif.")
    payload={"model":settings['model'],"instructions":instructions,"input":[{"role":"developer","content":"Contexte récent du salon:\n"+context},{"role":"user","content":query}],"max_output_tokens":500}
    req=urlrequest.Request('https://api.openai.com/v1/responses',data=json.dumps(payload).encode('utf-8'),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='POST')
    try:
        with urlrequest.urlopen(req,timeout=45) as resp: data=json.loads(resp.read().decode('utf-8'))
    except HTTPError as e:
        try: detail=json.loads(e.read().decode('utf-8')).get('error',{}).get('message','')
        except Exception: detail=''
        raise AIError('OpenAI a refusé la requête'+(': '+detail[:220] if detail else '.'))
    except URLError: raise AIError("Impossible de joindre le service IA. Vérifie Internet.")
    texts=[]
    for item in data.get('output',[]):
        if item.get('type')!='message': continue
        for part in item.get('content',[]):
            if part.get('type')=='output_text' and part.get('text'): texts.append(part['text'])
    text='\n'.join(texts).strip()
    if not text: raise AIError("L'IA n'a renvoyé aucun texte.")
    return text[:4000]

async def maybe_build_ai_reply(room_id,sender,content):
    settings=get_ai_settings()
    if not settings['enabled']: return None
    query=_extract_query(content,settings['trigger_name'])
    if query is None: return None
    bot_id=ensure_ai_user()
    try:
        if settings['provider']=='openai': answer=await asyncio.to_thread(_openai_sync,query,sender,room_id,settings)
        else: answer=_local_answer(query,sender,room_id)
    except AIError as e: answer='⚠️ PiAI : '+str(e)
    return save_message(room_id,bot_id,answer)
