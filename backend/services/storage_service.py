from __future__ import annotations

import hashlib
import io
import mimetypes
import re
import secrets
from pathlib import Path
from typing import Any, Dict, Optional

from config import (
    MAX_UPLOAD_BYTES, STORAGE_BACKEND, UPLOADS_DIR,
    S3_BUCKET, S3_ENDPOINT_URL, S3_REGION, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY,
)
from database import get_db_cursor


class StorageError(ValueError):
    pass


SAFE_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.gif', '.webp', '.pdf', '.txt', '.md', '.csv',
    '.docx', '.xlsx', '.pptx', '.odt', '.ods', '.odp', '.zip', '.json',
}


def _safe_name(name: str) -> str:
    base = Path(name or 'fichier').name[:180]
    stem = re.sub(r"[^A-Za-zÀ-ÖØ-öø-ÿ0-9._-]+", "_", Path(base).stem)[:90] or 'fichier'
    ext = Path(base).suffix.lower()
    return stem + ext


def _detect_mime(data: bytes, filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if data.startswith(b'\x89PNG\r\n\x1a\n'): return 'image/png'
    if data.startswith(b'\xff\xd8\xff'): return 'image/jpeg'
    if data[:6] in (b'GIF87a', b'GIF89a'): return 'image/gif'
    if data.startswith(b'RIFF') and data[8:12] == b'WEBP': return 'image/webp'
    if data.startswith(b'%PDF-'): return 'application/pdf'
    if data.startswith(b'PK\x03\x04'):
        return {
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            '.odt': 'application/vnd.oasis.opendocument.text',
            '.ods': 'application/vnd.oasis.opendocument.spreadsheet',
            '.odp': 'application/vnd.oasis.opendocument.presentation',
            '.zip': 'application/zip',
        }.get(ext, 'application/zip')
    if ext in {'.txt', '.md', '.csv', '.json'}:
        try:
            data[:65536].decode('utf-8')
            return 'application/json' if ext == '.json' else ('text/csv' if ext == '.csv' else 'text/plain')
        except UnicodeDecodeError:
            raise StorageError('Le contenu texte n’est pas un UTF-8 valide.')
    return mimetypes.guess_type(filename)[0] or 'application/octet-stream'


def validate_upload(data: bytes, filename: str, claimed_mime: str = '') -> str:
    if not data:
        raise StorageError('Le fichier est vide.')
    if len(data) > MAX_UPLOAD_BYTES:
        raise StorageError('Fichier trop volumineux.')
    ext = Path(filename or '').suffix.lower()
    if ext not in SAFE_EXTENSIONS:
        raise StorageError('Extension de fichier refusée.')
    detected = _detect_mime(data, filename)
    # Refuse known dangerous executable/script signatures regardless of extension.
    if data.startswith(b'MZ') or data.startswith(b'\x7fELF') or data.startswith(b'#!'):
        raise StorageError('Fichier exécutable ou script refusé.')
    claimed = (claimed_mime or '').lower().split(';', 1)[0].strip()
    if claimed and claimed not in {'application/octet-stream', 'binary/octet-stream'}:
        # Browser MIME may vary for Office/ZIP, so compare broad families there.
        if ext not in {'.zip', '.docx', '.xlsx', '.pptx', '.odt', '.ods', '.odp'}:
            if claimed.split('/', 1)[0] != detected.split('/', 1)[0] and claimed != detected:
                raise StorageError('Le type MIME déclaré ne correspond pas au contenu.')
    return detected


def _s3_client():
    if not (S3_BUCKET and S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY):
        raise StorageError('Stockage S3 incomplet : bucket ou identifiants absents.')
    try:
        import boto3
    except Exception as exc:
        raise StorageError('boto3 est requis pour le stockage S3.') from exc
    return boto3.client(
        's3',
        endpoint_url=S3_ENDPOINT_URL or None,
        region_name=S3_REGION or None,
        aws_access_key_id=S3_ACCESS_KEY_ID,
        aws_secret_access_key=S3_SECRET_ACCESS_KEY,
    )


def put_object(data: bytes, filename: str, content_type: str, created_by: Optional[int] = None, prefix: str = 'uploads') -> Dict[str, Any]:
    safe = _safe_name(filename)
    detected = validate_upload(data, safe, content_type)
    digest = hashlib.sha256(data).hexdigest()
    key = f"{prefix.strip('/')}/{secrets.token_hex(16)}_{safe}"
    backend = STORAGE_BACKEND
    external_url = ''
    db_data = data
    if backend == 'local':
        path = UPLOADS_DIR / key.split('/', 1)[-1]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        external_url = '/uploads/' + path.name
        db_data = None
    elif backend == 's3':
        client = _s3_client()
        client.put_object(Bucket=S3_BUCKET, Key=key, Body=data, ContentType=detected)
        db_data = None
    with get_db_cursor() as c:
        c.execute(
            """INSERT INTO file_objects(object_key,original_name,content_type,size_bytes,sha256,data,storage_backend,external_url,created_by)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (key, safe, detected, len(data), digest, db_data, backend, external_url, created_by),
        )
    return {
        'key': key, 'name': safe, 'mime': detected, 'size': len(data), 'sha256': digest,
        'backend': backend, 'url': external_url or ('/api/files/' + key),
    }


def get_object(key: str) -> Dict[str, Any]:
    with get_db_cursor() as c:
        row = c.execute("SELECT * FROM file_objects WHERE object_key=?", (key,)).fetchone()
    if not row:
        raise FileNotFoundError(key)
    backend = str(row['storage_backend'] or 'database')
    data = row['data']
    if backend == 'local':
        name = Path(str(row['external_url'] or '')).name
        data = (UPLOADS_DIR / name).read_bytes()
    elif backend == 's3':
        obj = _s3_client().get_object(Bucket=S3_BUCKET, Key=key)
        data = obj['Body'].read()
    if isinstance(data, memoryview):
        data = data.tobytes()
    return {
        'data': bytes(data or b''),
        'name': str(row['original_name']),
        'mime': str(row['content_type'] or 'application/octet-stream'),
        'size': int(row['size_bytes'] or 0),
        'sha256': str(row['sha256'] or ''),
        'backend': backend,
    }


def list_objects(limit: int = 100) -> list[dict]:
    with get_db_cursor() as c:
        rows = c.execute(
            "SELECT object_key,original_name,content_type,size_bytes,sha256,storage_backend,created_at FROM file_objects ORDER BY created_at DESC LIMIT ?",
            (max(1, min(int(limit), 500)),),
        ).fetchall()
    return [dict(r) for r in rows]


def storage_stats() -> Dict[str, Any]:
    with get_db_cursor() as c:
        row = c.execute("SELECT COUNT(*) AS n,COALESCE(SUM(size_bytes),0) AS bytes FROM file_objects").fetchone()
    return {'backend': STORAGE_BACKEND, 'objects': int(row['n'] or 0), 'bytes': int(row['bytes'] or 0)}
