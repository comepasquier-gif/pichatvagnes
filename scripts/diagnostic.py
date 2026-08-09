#!/usr/bin/env python3
"""Diagnostic local/CI PiChat 3.4, sans afficher de secrets."""
from __future__ import annotations
import json, os, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT)]
from database import init_database, get_db_cursor  # noqa: E402
from config import APP_VERSION, DATABASE_BACKEND, STORAGE_BACKEND, PICHAT_SECRET_KEY  # noqa: E402

def main():
    init_database()
    with get_db_cursor() as c:
        migrations=[r['version'] for r in c.execute('SELECT version FROM schema_migrations ORDER BY version').fetchall()]
        users=int(c.execute('SELECT COUNT(*) AS n FROM users').fetchone()['n'])
    result={
        'ok': True,'version':APP_VERSION,'python':sys.version.split()[0],
        'database_backend':DATABASE_BACKEND,'storage_backend':STORAGE_BACKEND,
        'secret_configured':bool(PICHAT_SECRET_KEY),'migrations':migrations,'users':users,
        'render_yaml':(ROOT/'render.yaml').exists(),'dockerfile':(ROOT/'Dockerfile').exists(),
    }
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
