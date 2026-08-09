from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import re
import shutil
import secrets
import mimetypes
import sqlite3
import tempfile
import threading
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Optional, Any

from config import BACKUPS_DIR, DATABASE_BACKEND, DATABASE_PATH
from database import get_db_cursor, get_connection, is_postgres
from services.storage_service import validate_upload, StorageError

MAX_IMPORTED_BACKUP = 1024 * 1024 * 1024
MAX_FILE_INJECTION = 25 * 1024 * 1024
_BACKUP_LOCK = threading.RLock()
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._ -]+")
EXCLUDED_TABLES = {
    'backup_archives', 'sessions', 'login_attempts', 'support_access_links', 'support_sessions'
}


def _safe_backup_name(name: str, ensure_zip: bool = True) -> str:
    name = Path(str(name)).name.strip()
    name = _SAFE_NAME.sub('_', name).strip(' .')
    if not name: raise ValueError('Nom de sauvegarde vide.')
    if ensure_zip and not name.lower().endswith('.zip'): name += '.zip'
    if len(name) > 140: name = Path(name).stem[:130] + '.zip'
    return name


def _db_archive_row(name: str):
    try:
        with get_db_cursor() as c:
            return c.execute('SELECT * FROM backup_archives WHERE name=?', (_safe_backup_name(name),)).fetchone()
    except Exception:
        return None


def _materialize(name: str) -> Path:
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    safe = _safe_backup_name(name)
    path = BACKUPS_DIR / safe
    row = _db_archive_row(safe)
    if row and row['archive_data'] is not None:
        data = row['archive_data'].tobytes() if isinstance(row['archive_data'], memoryview) else bytes(row['archive_data'])
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != str(row['sha256']):
            path.write_bytes(data)
    return path


def _backup_path(name: str) -> Path:
    path = _materialize(name)
    if path.parent.resolve() != BACKUPS_DIR.resolve(): raise ValueError('Chemin de sauvegarde invalide.')
    return path


def _persist_archive(path: Path, label: str = '', note: str = '') -> None:
    if not path.exists(): return
    data = path.read_bytes(); digest = hashlib.sha256(data).hexdigest()
    try:
        with zipfile.ZipFile(path) as z:
            m = _read_manifest(z)
            label = label or str(m.get('label') or '')
            note = note or str(m.get('note') or '')
        with get_db_cursor() as c:
            c.execute(
                """INSERT INTO backup_archives(name,sha256,size_bytes,archive_data,storage_backend,integrity_status,label,note)
                   VALUES (?,?,?,?,?,'ok',?,?)
                   ON CONFLICT(name) DO UPDATE SET sha256=excluded.sha256,size_bytes=excluded.size_bytes,
                     archive_data=excluded.archive_data,storage_backend=excluded.storage_backend,integrity_status='ok',
                     label=excluded.label,note=excluded.note""",
                (path.name, digest, len(data), data, 'database', label[:100], note[:500]),
            )
    except Exception:
        # Local mode can still work if 3.4 migration tables are unavailable during a repair.
        pass


def _validate_member_name(name: str) -> None:
    p = PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts: raise ValueError('Chemin dangereux dans le ZIP : %s' % name)


def _read_manifest(z: zipfile.ZipFile) -> dict:
    try: manifest = json.loads(z.read('backup_manifest.json').decode('utf-8'))
    except KeyError as exc: raise ValueError('Manifeste PiChat absent.') from exc
    except Exception as exc: raise ValueError('Manifeste illisible.') from exc
    if manifest.get('format') != 'pichat-backup' or int(manifest.get('format_version', 0)) not in {1,2}:
        raise ValueError('Format de backup incompatible.')
    return manifest


def validate_backup(path: Path) -> dict:
    if not path.is_file() or not zipfile.is_zipfile(path): raise ValueError("Le fichier n'est pas un ZIP valide.")
    with zipfile.ZipFile(path, 'r') as z:
        for item in z.infolist(): _validate_member_name(item.filename)
        bad = z.testzip()
        if bad: raise ValueError('Fichier corrompu dans l’archive : %s' % bad)
        manifest = _read_manifest(z); names = set(z.namelist())
        version = int(manifest.get('format_version', 0))
        if version == 1 and manifest.get('database_included') and 'database/pichat.db' not in names:
            raise ValueError('Base database/pichat.db absente.')
        if version == 2 and 'database/export.json' not in names:
            raise ValueError('Export database/export.json absent.')
        upload_names = [n for n in names if n.startswith('uploads/') and not n.endswith('/') and n != 'uploads/.gitkeep']
    return {'manifest': manifest, 'upload_names': sorted(upload_names)}


def _table_names() -> list[str]:
    with get_db_cursor() as c:
        if is_postgres():
            rows = c.execute("SELECT table_name AS name FROM information_schema.tables WHERE table_schema=current_schema() AND table_type='BASE TABLE' ORDER BY table_name").fetchall()
        else:
            rows = c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
    return [str(r['name']) for r in rows if str(r['name']) not in EXCLUDED_TABLES]


def _encode(v: Any):
    if isinstance(v, memoryview): v = v.tobytes()
    if isinstance(v, (bytes, bytearray)):
        return {'__pichat_bytes__': base64.b64encode(bytes(v)).decode('ascii')}
    if isinstance(v, (str,int,float,bool)) or v is None: return v
    return str(v)


def _decode(v: Any):
    if isinstance(v, dict) and set(v) == {'__pichat_bytes__'}:
        return base64.b64decode(v['__pichat_bytes__'])
    return v


def _export_database() -> tuple[dict, dict[str,int]]:
    payload = {'schema': 'pichat-portable-v2', 'tables': {}}
    counts = {}
    for table in _table_names():
        try:
            with get_db_cursor() as c:
                rows = c.execute('SELECT * FROM "%s"' % table).fetchall()
            clean=[]
            for row in rows:
                d={k:_encode(row[k]) for k in row.keys()}
                if table == 'api_integrations':
                    # API secrets are intentionally excluded from exportable backups.
                    d['encrypted_api_key'] = ''
                clean.append(d)
            payload['tables'][table]=clean; counts[table]=len(clean)
        except Exception:
            continue
    return payload, counts


def create_backup(label: str = '', note: str = '') -> Path:
    with _BACKUP_LOCK:
        BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
        stamp=datetime.now().strftime('%Y%m%d_%H%M%S'); output=BACKUPS_DIR/f'PiChat_backup_{stamp}.zip'; i=2
        while output.exists() or _db_archive_row(output.name): output=BACKUPS_DIR/f'PiChat_backup_{stamp}_{i}.zip'; i+=1
        export, counts = _export_database()
        manifest={
            'format':'pichat-backup','format_version':2,'app_version':'3.4.0',
            'created_at':datetime.now().astimezone().isoformat(timespec='seconds'),
            'database_included':True,'database_file':'database/export.json','table_counts':counts,
            'upload_file_count':int(counts.get('file_objects',0)),
            'label':(label or '').strip()[:100],'note':(note or '').strip()[:500],'edited_at':None,
            'secrets_excluded':['api_integrations.encrypted_api_key','sessions','login_attempts','support_access_links','support_sessions'],
        }
        with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
            z.writestr('backup_manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
            z.writestr('database/export.json',json.dumps(export,ensure_ascii=False,separators=(',',':')))
            # Friendly human-readable inventory without hashes or secrets.
            z.writestr('README_RESTAURATION.txt','Backup portable PiChat 3.4. Les clés API et tokens de session sont exclus.\n')
        validate_backup(output); _persist_archive(output,label,note); return output


def backup_info(path: Path) -> dict:
    path=_backup_path(path.name if isinstance(path,Path) else str(path)); stat=path.stat()
    base={'name':path.name,'size':stat.st_size,'modified_at':datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec='seconds')}
    try:
        check=validate_backup(path); m=check['manifest']; counts=m.get('table_counts') or {}
        base.update({'valid':True,'error':None,'created_at':m.get('created_at'),'label':m.get('label') or '', 'note':m.get('note') or '',
                     'edited_at':m.get('edited_at'),'counts':counts,'users':int(counts.get('users',0)),'rooms':int(counts.get('rooms',0)),
                     'messages':int(counts.get('messages',0))+int(counts.get('private_messages',0)),'uploads':int(m.get('upload_file_count',0) or 0)})
    except Exception as exc:
        base.update({'valid':False,'error':str(exc),'created_at':None,'label':'','note':'','counts':{},'users':0,'rooms':0,'messages':0,'uploads':0})
    return base


def _materialize_all() -> None:
    BACKUPS_DIR.mkdir(parents=True,exist_ok=True)
    try:
        with get_db_cursor() as c: rows=c.execute('SELECT name FROM backup_archives ORDER BY created_at DESC').fetchall()
        for r in rows: _materialize(str(r['name']))
    except Exception: pass


def list_backups() -> list[dict]:
    _materialize_all()
    return sorted((backup_info(p) for p in BACKUPS_DIR.glob('*.zip') if p.is_file()),key=lambda x:x.get('created_at') or x['modified_at'],reverse=True)


def _v2_file_inventory(path: Path) -> list[dict]:
    with zipfile.ZipFile(path) as z:
        export=json.loads(z.read('database/export.json').decode('utf-8'))
    rows=(export.get('tables') or {}).get('file_objects') or []
    files=[]
    for row in rows:
        key=str(row.get('object_key') or '')
        if not key: continue
        files.append({
            'path':key,
            'name':str(row.get('original_name') or Path(key).name),
            'size':int(row.get('size_bytes') or 0),
            'mime':str(row.get('content_type') or 'application/octet-stream'),
            'sha256':str(row.get('sha256') or ''),
        })
    return files


def inspect_backup(name: str) -> dict:
    p=_backup_path(name); check=validate_backup(p); info=backup_info(p); info['manifest']=check['manifest']
    if int(check['manifest'].get('format_version',0))==2:
        info['files']=_v2_file_inventory(p)
    else:
        info['files']=[{'path':n,'name':Path(n).name,'size':_member_size(p,n)} for n in check['upload_names']]
    return info


def _member_size(path: Path, member: str) -> int:
    with zipfile.ZipFile(path) as z:
        try:return int(z.getinfo(member).file_size)
        except KeyError:return 0


def _rewrite_archive(path: Path, transform, extra_members: Optional[list[tuple[str,bytes]]]=None) -> None:
    with tempfile.NamedTemporaryFile(prefix='pichat_backup_edit_',suffix='.zip',dir=path.parent,delete=False) as fh: tmp=Path(fh.name)
    try:
        with zipfile.ZipFile(path,'r') as src,zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED) as dst:
            for item in src.infolist():
                result=transform(item.filename,src.read(item.filename))
                if result is not None: dst.writestr(result[0],result[1])
            for n,d in extra_members or []: dst.writestr(n,d)
        validate_backup(tmp); tmp.replace(path); _persist_archive(path)
    except Exception: tmp.unlink(missing_ok=True); raise


def update_metadata(name: str,label: str,note: str) -> dict:
    p=_backup_path(name); validate_backup(p)
    def tr(n,d):
        if n=='backup_manifest.json':
            m=json.loads(d);m['label']=(label or '')[:100];m['note']=(note or '')[:500];m['edited_at']=datetime.now().astimezone().isoformat(timespec='seconds');d=json.dumps(m,ensure_ascii=False,indent=2).encode()
        return n,d
    _rewrite_archive(p,tr);_persist_archive(p,label,note);return inspect_backup(p.name)


def rename_backup(name: str,new_name: str) -> dict:
    src=_backup_path(name);dst=BACKUPS_DIR/_safe_backup_name(new_name)
    if dst.exists() or _db_archive_row(dst.name): raise FileExistsError('Une sauvegarde porte déjà ce nom.')
    src.rename(dst)
    try:
        with get_db_cursor() as c: c.execute('DELETE FROM backup_archives WHERE name=?',(src.name,))
    except Exception: pass
    _persist_archive(dst);return backup_info(dst)


def duplicate_backup(name: str,new_name: Optional[str]=None) -> dict:
    src=_backup_path(name);validate_backup(src)
    if new_name: dst=BACKUPS_DIR/_safe_backup_name(new_name)
    else:
        dst=BACKUPS_DIR/(src.stem+'_copie.zip');i=2
        while dst.exists() or _db_archive_row(dst.name):dst=BACKUPS_DIR/(src.stem+f'_copie_{i}.zip');i+=1
    if dst.exists():raise FileExistsError('La copie existe déjà.')
    shutil.copy2(src,dst);_persist_archive(dst);return backup_info(dst)


def delete_backup(name: str)->None:
    p=_backup_path(name);p.unlink(missing_ok=True)
    try:
        with get_db_cursor() as c:c.execute('DELETE FROM backup_archives WHERE name=?',(_safe_backup_name(name),))
    except Exception:pass


def import_backup(fileobj: BinaryIO,original_name: str)->dict:
    BACKUPS_DIR.mkdir(parents=True,exist_ok=True);name=_safe_backup_name(original_name);dst=BACKUPS_DIR/name;i=2
    while dst.exists() or _db_archive_row(dst.name):dst=BACKUPS_DIR/f'{Path(name).stem}_{i}.zip';i+=1
    total=0
    with tempfile.NamedTemporaryFile(prefix='pichat_import_',suffix='.zip',dir=BACKUPS_DIR,delete=False) as fh:
        tmp=Path(fh.name)
        while True:
            chunk=fileobj.read(1024*1024)
            if not chunk:break
            total+=len(chunk)
            if total>MAX_IMPORTED_BACKUP:raise ValueError('Backup trop volumineux (maximum 1 Go).')
            fh.write(chunk)
    try:validate_backup(tmp);tmp.replace(dst);_persist_archive(dst)
    except Exception:tmp.unlink(missing_ok=True);raise
    return backup_info(dst)


def _rewrite_v2_export(path: Path, mutate) -> None:
    with zipfile.ZipFile(path) as z:
        manifest=_read_manifest(z)
        export=json.loads(z.read('database/export.json').decode('utf-8'))
    mutate(export,manifest)
    tables=export.setdefault('tables',{})
    manifest['table_counts']={k:len(v or []) for k,v in tables.items()}
    manifest['upload_file_count']=len(tables.get('file_objects') or [])
    manifest['edited_at']=datetime.now().astimezone().isoformat(timespec='seconds')
    def tr(n,d):
        if n=='backup_manifest.json': return n,json.dumps(manifest,ensure_ascii=False,indent=2).encode('utf-8')
        if n=='database/export.json': return n,json.dumps(export,ensure_ascii=False,separators=(',',':')).encode('utf-8')
        return n,d
    _rewrite_archive(path,tr)


def add_upload_file(name: str,fileobj: BinaryIO,filename: str)->dict:
    p=_backup_path(name);check=validate_backup(p);safe=Path(str(filename or 'fichier')).name[:180]
    data=fileobj.read(MAX_FILE_INJECTION+1)
    if len(data)>MAX_FILE_INJECTION: raise ValueError('Fichier trop volumineux pour un backup (25 Mo maximum).')
    try:mime=validate_upload(data,safe,mimetypes.guess_type(safe)[0] or 'application/octet-stream')
    except StorageError as exc: raise ValueError(str(exc)) from exc
    if int(check['manifest'].get('format_version',0))==1:
        # Preserve the old editable ZIP behaviour for legacy backups.
        member='uploads/'+safe
        def tr(n,d): return None if n==member else (n,d)
        _rewrite_archive(p,tr,[(member,data)])
        return inspect_backup(p.name)
    digest=hashlib.sha256(data).hexdigest();key=f"uploads/backup_{secrets.token_hex(8)}_{safe}"
    encoded=_encode(data)
    def mutate(export,manifest):
        rows=export.setdefault('tables',{}).setdefault('file_objects',[])
        rows.append({
            'object_key':key,'original_name':safe,'content_type':mime,'size_bytes':len(data),
            'sha256':digest,'data':encoded,'storage_backend':'database','external_url':'',
            'created_by':None,'created_at':datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        })
    _rewrite_v2_export(p,mutate);return inspect_backup(p.name)

def remove_upload_file(name: str,member: str)->dict:
    p=_backup_path(name);check=validate_backup(p);member=str(member or '').lstrip('/')
    if not member.startswith('uploads/'): raise ValueError('Seuls les fichiers du backup peuvent être retirés.')
    if int(check['manifest'].get('format_version',0))==1:
        if member not in check['upload_names']: raise FileNotFoundError(member)
        def tr(n,d): return None if n==member else (n,d)
        _rewrite_archive(p,tr);return inspect_backup(p.name)
    found={'ok':False}
    def mutate(export,manifest):
        rows=export.setdefault('tables',{}).setdefault('file_objects',[])
        kept=[]
        for row in rows:
            if str(row.get('object_key') or '')==member: found['ok']=True
            else: kept.append(row)
        export['tables']['file_objects']=kept
    _rewrite_v2_export(p,mutate)
    if not found['ok']: raise FileNotFoundError(member)
    return inspect_backup(p.name)

def read_backup_upload(name: str,member: str)->dict:
    p=_backup_path(name);check=validate_backup(p);member=str(member or '').lstrip('/')
    if int(check['manifest'].get('format_version',0))==1:
        if member not in check['upload_names']: raise FileNotFoundError(member)
        with zipfile.ZipFile(p) as z:data=z.read(member)
        filename=Path(member).name;return {'data':data,'name':filename,'mime':mimetypes.guess_type(filename)[0] or 'application/octet-stream'}
    with zipfile.ZipFile(p) as z:export=json.loads(z.read('database/export.json').decode('utf-8'))
    for row in (export.get('tables') or {}).get('file_objects') or []:
        if str(row.get('object_key') or '')==member:
            data=_decode(row.get('data'))
            if data is None: raise ValueError('Ce backup référence un objet externe sans copie binaire.')
            return {'data':bytes(data),'name':str(row.get('original_name') or Path(member).name),'mime':str(row.get('content_type') or 'application/octet-stream')}
    raise FileNotFoundError(member)


def accounts_csv(name: str)->bytes:
    p=_backup_path(name);check=validate_backup(p)
    with zipfile.ZipFile(p) as z:
        if int(check['manifest'].get('format_version',0))==2:
            data=json.loads(z.read('database/export.json')); rows=data.get('tables',{}).get('users',[])
            wanted=['id','username','class_code','is_admin','is_moderator','moderator_class_code','is_banned','grade_title','created_at']
            out=io.StringIO();w=csv.writer(out);w.writerow(wanted)
            for r in sorted(rows,key=lambda x:str(x.get('username','')).lower()):w.writerow([r.get(k) for k in wanted])
            return ('\ufeff'+out.getvalue()).encode('utf-8')
        # Legacy 3.3 backup
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'pichat.db';db.write_bytes(z.read('database/pichat.db'));conn=sqlite3.connect(db);conn.row_factory=sqlite3.Row
            cols={r[1] for r in conn.execute('PRAGMA table_info(users)')};wanted=[c for c in ['id','username','class_code','is_admin','is_moderator','moderator_class_code','is_banned','grade_title','created_at'] if c in cols]
            rows=conn.execute('SELECT '+','.join(wanted)+' FROM users ORDER BY username COLLATE NOCASE').fetchall();conn.close();out=io.StringIO();w=csv.writer(out);w.writerow(wanted);w.writerows([[r[c] for c in wanted] for r in rows]);return ('\ufeff'+out.getvalue()).encode('utf-8')


def _restore_v2(path: Path) -> None:
    with zipfile.ZipFile(path) as z: export=json.loads(z.read('database/export.json').decode('utf-8'))
    tables=export.get('tables') or {}
    # Only restore tables that still exist in the current schema; migrations remain authoritative.
    current=set(_table_names())
    selected=[t for t in tables if t in current and t not in {'schema_migrations'}]
    if is_postgres():
        if selected:
            with get_db_cursor() as c:c.execute('TRUNCATE TABLE '+','.join('"%s"'%t for t in selected)+' CASCADE')
        for table in selected:
            for row in tables[table]:
                if not row:continue
                cols=list(row.keys());vals=[_decode(row[k]) for k in cols]
                with get_db_cursor() as c:c.execute('INSERT INTO "%s" (%s) VALUES (%s)'%(table,','.join('"%s"'%k for k in cols),','.join('?' for _ in cols)),tuple(vals))
        # Reset serial sequences after explicit id restoration.
        with get_db_cursor() as c:
            for table in selected:
                if tables[table] and 'id' in tables[table][0]:
                    seq=c.execute("SELECT pg_get_serial_sequence(?, 'id') AS seq",(table,)).fetchone()
                    if seq and seq['seq']:
                        max_id=max(int(r.get('id') or 0) for r in tables[table])
                        c.execute('SELECT setval(?, ?, ?)',(seq['seq'],max(1,max_id),bool(max_id)))
    else:
        conn=sqlite3.connect(DATABASE_PATH);conn.execute('PRAGMA foreign_keys=OFF')
        try:
            for table in selected:conn.execute('DELETE FROM "%s"'%table)
            for table in selected:
                for row in tables[table]:
                    cols=list(row.keys());vals=[_decode(row[k]) for k in cols]
                    conn.execute('INSERT INTO "%s" (%s) VALUES (%s)'%(table,','.join('"%s"'%k for k in cols),','.join('?' for _ in cols)),vals)
            conn.commit()
        finally:conn.execute('PRAGMA foreign_keys=ON');conn.close()


def restore_backup(name: str)->dict:
    p=_backup_path(name);check=validate_backup(p);m=check['manifest'];safety=create_backup(label='Sécurité avant restauration',note='Créé automatiquement avant restauration de '+p.name)
    if int(m.get('format_version',0))==2:
        _restore_v2(p);return {'restored':p.name,'safety_backup':safety.name,'format_version':2}
    # Legacy SQLite backup restore is only safe into SQLite. Use migrate_sqlite_to_postgres.py for online mode.
    if is_postgres():raise ValueError('Backup SQLite 3.3 détecté. Utilise scripts/migrate_sqlite_to_postgres.py pour une migration PostgreSQL contrôlée.')
    with _BACKUP_LOCK,tempfile.TemporaryDirectory(prefix='pichat_restore_') as td,zipfile.ZipFile(p) as z:
        db=Path(td)/'pichat.db';db.write_bytes(z.read('database/pichat.db'))
        with sqlite3.connect(db) as conn:conn.execute('PRAGMA integrity_check').fetchone()
        staged=DATABASE_PATH.with_suffix('.db.restore_tmp');shutil.copy2(db,staged);staged.replace(DATABASE_PATH)
    return {'restored':p.name,'safety_backup':safety.name,'format_version':1}
