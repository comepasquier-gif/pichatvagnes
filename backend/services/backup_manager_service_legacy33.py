from __future__ import annotations

import csv
import io
import json
import os
import re
import shutil
import sqlite3
import tempfile
import threading
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Optional

from config import DATABASE_PATH, PROJECT_ROOT, UPLOADS_DIR, BACKUPS_DIR

FRIENDLY_URL_CONFIG = PROJECT_ROOT / "friendly_url.json"
MAX_IMPORTED_BACKUP = 1024 * 1024 * 1024  # 1 Go
MAX_FILE_INJECTION = 25 * 1024 * 1024
_BACKUP_LOCK = threading.RLock()
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._ -]+")


def _safe_backup_name(name: str, ensure_zip: bool = True) -> str:
    name = Path(str(name)).name.strip()
    name = _SAFE_NAME.sub("_", name).strip(" .")
    if not name:
        raise ValueError("Nom de sauvegarde vide.")
    if ensure_zip and not name.lower().endswith(".zip"):
        name += ".zip"
    if len(name) > 140:
        stem, suffix = Path(name).stem[:130], ".zip"
        name = stem + suffix
    return name


def _backup_path(name: str) -> Path:
    safe = _safe_backup_name(name)
    path = (BACKUPS_DIR / safe).resolve()
    if path.parent != BACKUPS_DIR.resolve():
        raise ValueError("Chemin de sauvegarde invalide.")
    return path


def _validate_member_name(name: str) -> None:
    p = PurePosixPath(name)
    if p.is_absolute() or ".." in p.parts:
        raise ValueError(f"Chemin dangereux dans le ZIP : {name}")


def _read_manifest(z: zipfile.ZipFile) -> dict:
    try:
        manifest = json.loads(z.read("backup_manifest.json").decode("utf-8"))
    except KeyError as exc:
        raise ValueError("Manifeste PiChat absent.") from exc
    except Exception as exc:
        raise ValueError("Manifeste illisible.") from exc
    if manifest.get("format") != "pichat-backup" or int(manifest.get("format_version", 0)) != 1:
        raise ValueError("Format de backup incompatible.")
    return manifest


def validate_backup(path: Path) -> dict:
    if not path.is_file() or not zipfile.is_zipfile(path):
        raise ValueError("Le fichier n'est pas un ZIP valide.")
    with zipfile.ZipFile(path, "r") as z:
        for item in z.infolist():
            _validate_member_name(item.filename)
        bad = z.testzip()
        if bad:
            raise ValueError(f"Fichier corrompu dans l'archive : {bad}")
        manifest = _read_manifest(z)
        names = set(z.namelist())
        if manifest.get("database_included") and "database/pichat.db" not in names:
            raise ValueError("Base database/pichat.db absente.")
        upload_names = [n for n in names if n.startswith("uploads/") and not n.endswith("/") and n != "uploads/.gitkeep"]
    return {"manifest": manifest, "upload_names": sorted(upload_names)}


def _table_counts(db_path: Path) -> dict[str, int]:
    if not db_path.exists():
        return {}
    counts = {}
    with sqlite3.connect(db_path) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        for table in sorted(tables):
            counts[table] = int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
    return counts


def create_backup(label: str = "", note: str = "") -> Path:
    with _BACKUP_LOCK:
        BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = BACKUPS_DIR / f"PiChat_backup_{stamp}.zip"
        index = 2
        while output.exists():
            output = BACKUPS_DIR / f"PiChat_backup_{stamp}_{index}.zip"; index += 1
        with tempfile.TemporaryDirectory(prefix="pichat_backup_") as tmp:
            snapshot = Path(tmp) / "pichat.db"
            db_included = DATABASE_PATH.exists()
            if db_included:
                with sqlite3.connect(DATABASE_PATH) as src, sqlite3.connect(snapshot) as dst:
                    src.backup(dst)
            counts = _table_counts(snapshot) if db_included else {}
            uploads = [p for p in UPLOADS_DIR.rglob("*") if p.is_file() and p.name != ".gitkeep"] if UPLOADS_DIR.exists() else []
            manifest = {
                "format": "pichat-backup", "format_version": 1,
                "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "database_included": db_included,
                "database_file": "database/pichat.db" if db_included else None,
                "uploads_prefix": "uploads/", "upload_file_count": len(uploads),
                "table_counts": counts, "friendly_url_config_included": FRIENDLY_URL_CONFIG.exists(),
                "label": (label or "").strip()[:100], "note": (note or "").strip()[:500],
                "edited_at": None,
            }
            with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("backup_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
                if db_included: z.write(snapshot, "database/pichat.db")
                if FRIENDLY_URL_CONFIG.exists(): z.write(FRIENDLY_URL_CONFIG, "config/friendly_url.json")
                if UPLOADS_DIR.exists():
                    for f in sorted(UPLOADS_DIR.rglob("*")):
                        if f.is_file(): z.write(f, str(PurePosixPath("uploads") / PurePosixPath(f.relative_to(UPLOADS_DIR).as_posix())))
                else: z.writestr("uploads/.gitkeep", "")
        return output


def backup_info(path: Path) -> dict:
    stat = path.stat()
    base = {"name": path.name, "size": stat.st_size, "modified_at": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds")}
    try:
        check = validate_backup(path)
        m = check["manifest"]
        counts = m.get("table_counts") or {}
        base.update({
            "valid": True, "error": None, "created_at": m.get("created_at"), "label": m.get("label") or "",
            "note": m.get("note") or "", "edited_at": m.get("edited_at"), "counts": counts,
            "users": int(counts.get("users", 0)), "rooms": int(counts.get("rooms", 0)),
            "messages": int(counts.get("messages", 0)) + int(counts.get("private_messages", 0)),
            "uploads": int(m.get("upload_file_count", len(check["upload_names"])) or 0),
        })
    except Exception as exc:
        base.update({"valid": False, "error": str(exc), "created_at": None, "label": "", "note": "", "counts": {}, "users": 0, "rooms": 0, "messages": 0, "uploads": 0})
    return base


def list_backups() -> list[dict]:
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    return sorted((backup_info(p) for p in BACKUPS_DIR.glob("*.zip") if p.is_file()), key=lambda x: x.get("created_at") or x["modified_at"], reverse=True)


def inspect_backup(name: str) -> dict:
    path = _backup_path(name)
    check = validate_backup(path)
    info = backup_info(path)
    info["manifest"] = check["manifest"]
    info["files"] = [{"path": n, "size": _member_size(path, n)} for n in check["upload_names"]]
    return info


def _member_size(path: Path, member: str) -> int:
    with zipfile.ZipFile(path) as z:
        try: return int(z.getinfo(member).file_size)
        except KeyError: return 0


def _rewrite_archive(path: Path, transform, extra_members: Optional[list[tuple[str, bytes]]] = None) -> None:
    with _BACKUP_LOCK, tempfile.NamedTemporaryFile(prefix="pichat_backup_edit_", suffix=".zip", dir=path.parent, delete=False) as fh:
        tmp = Path(fh.name)
    try:
        with zipfile.ZipFile(path, "r") as src, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
            for item in src.infolist():
                data = src.read(item.filename)
                result = transform(item.filename, data)
                if result is None: continue
                out_name, out_data = result
                dst.writestr(out_name, out_data)
            for n, data in extra_members or []:
                dst.writestr(n, data)
        validate_backup(tmp)
        tmp.replace(path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def update_metadata(name: str, label: str, note: str) -> dict:
    path = _backup_path(name); validate_backup(path)
    def transform(n, data):
        if n == "backup_manifest.json":
            m = json.loads(data.decode("utf-8")); m["label"]=(label or "").strip()[:100]; m["note"]=(note or "").strip()[:500]; m["edited_at"]=datetime.now().astimezone().isoformat(timespec="seconds")
            data=json.dumps(m,ensure_ascii=False,indent=2).encode()
        return n,data
    _rewrite_archive(path, transform)
    return inspect_backup(path.name)


def rename_backup(name: str, new_name: str) -> dict:
    src = _backup_path(name); validate_backup(src)
    dst = _backup_path(new_name)
    if dst.exists(): raise FileExistsError("Une sauvegarde porte déjà ce nom.")
    src.rename(dst); return backup_info(dst)


def duplicate_backup(name: str, new_name: Optional[str] = None) -> dict:
    src = _backup_path(name); validate_backup(src)
    if new_name: dst = _backup_path(new_name)
    else:
        dst = src.with_name(src.stem + "_copie.zip"); i=2
        while dst.exists(): dst=src.with_name(src.stem+f"_copie_{i}.zip"); i+=1
    if dst.exists(): raise FileExistsError("La copie existe déjà.")
    shutil.copy2(src,dst); return backup_info(dst)


def delete_backup(name: str) -> None:
    path = _backup_path(name); path.unlink()


def import_backup(fileobj: BinaryIO, original_name: str) -> dict:
    BACKUPS_DIR.mkdir(parents=True,exist_ok=True)
    name=_safe_backup_name(original_name)
    dst=_backup_path(name)
    if dst.exists():
        stem=dst.stem; i=2
        while dst.exists(): dst=BACKUPS_DIR/f"{stem}_{i}.zip"; i+=1
    total=0
    with tempfile.NamedTemporaryFile(prefix="pichat_import_",suffix=".zip",dir=BACKUPS_DIR,delete=False) as fh:
        tmp=Path(fh.name)
        while True:
            chunk=fileobj.read(1024*1024)
            if not chunk: break
            total+=len(chunk)
            if total>MAX_IMPORTED_BACKUP: raise ValueError("Backup trop volumineux (maximum 1 Go).")
            fh.write(chunk)
    try:
        validate_backup(tmp); tmp.replace(dst)
    except Exception:
        tmp.unlink(missing_ok=True); raise
    return backup_info(dst)


def add_upload_file(name: str, fileobj: BinaryIO, filename: str) -> dict:
    path=_backup_path(name); check=validate_backup(path)
    clean=Path(filename).name.strip().replace("\\","_")
    clean=_SAFE_NAME.sub("_",clean).strip(" .") or "fichier"
    data=fileobj.read(MAX_FILE_INJECTION+1)
    if len(data)>MAX_FILE_INJECTION: raise ValueError("Fichier trop volumineux (maximum 25 Mo).")
    member=f"uploads/{clean}"
    names=set()
    def transform(n,d):
        names.add(n)
        if n==member: return None
        if n=="backup_manifest.json":
            m=json.loads(d.decode()); m["edited_at"]=datetime.now().astimezone().isoformat(timespec="seconds"); d=json.dumps(m,ensure_ascii=False,indent=2).encode()
        return n,d
    _rewrite_archive(path,transform,[(member,data)])
    _refresh_manifest_upload_count(path)
    return inspect_backup(path.name)


def remove_upload_file(name: str, member: str) -> dict:
    path=_backup_path(name); validate_backup(path)
    member=str(PurePosixPath(member))
    if not member.startswith("uploads/") or member in {"uploads/","uploads/.gitkeep"}: raise ValueError("Seuls les fichiers uploads peuvent être retirés.")
    found=False
    def transform(n,d):
        nonlocal found
        if n==member: found=True; return None
        if n=="backup_manifest.json":
            m=json.loads(d.decode()); m["edited_at"]=datetime.now().astimezone().isoformat(timespec="seconds"); d=json.dumps(m,ensure_ascii=False,indent=2).encode()
        return n,d
    _rewrite_archive(path,transform)
    if not found: raise FileNotFoundError("Fichier absent du backup.")
    _refresh_manifest_upload_count(path)
    return inspect_backup(path.name)


def _refresh_manifest_upload_count(path: Path) -> None:
    with zipfile.ZipFile(path) as z:
        count=sum(1 for n in z.namelist() if n.startswith("uploads/") and not n.endswith("/") and n!="uploads/.gitkeep")
    def transform(n,d):
        if n=="backup_manifest.json":
            m=json.loads(d.decode()); m["upload_file_count"]=count; m["edited_at"]=datetime.now().astimezone().isoformat(timespec="seconds"); d=json.dumps(m,ensure_ascii=False,indent=2).encode()
        return n,d
    _rewrite_archive(path,transform)


def accounts_csv(name: str) -> bytes:
    path=_backup_path(name); validate_backup(path)
    with tempfile.TemporaryDirectory(prefix="pichat_backup_db_") as td, zipfile.ZipFile(path) as z:
        if "database/pichat.db" not in z.namelist(): raise ValueError("Ce backup ne contient pas de base.")
        db=Path(td)/"pichat.db"; db.write_bytes(z.read("database/pichat.db"))
        conn=sqlite3.connect(db); conn.row_factory=sqlite3.Row
        cols={r[1] for r in conn.execute("PRAGMA table_info(users)")}
        wanted=[c for c in ["id","username","class_code","is_admin","is_moderator","moderator_class_code","is_banned","grade_title","created_at"] if c in cols]
        rows=conn.execute("SELECT "+",".join(wanted)+" FROM users ORDER BY username COLLATE NOCASE").fetchall(); conn.close()
    out=io.StringIO(); w=csv.writer(out); w.writerow(wanted); w.writerows([[r[c] for c in wanted] for r in rows]); return ('\ufeff'+out.getvalue()).encode('utf-8')


def restore_backup(name: str) -> dict:
    """Restauration à chaud pour une petite installation. Un backup de sécurité est créé avant."""
    path=_backup_path(name); check=validate_backup(path); manifest=check['manifest']
    if not manifest.get('database_included'): raise ValueError('Ce backup ne contient pas de base de données.')
    safety=create_backup(label='Sécurité avant restauration',note=f'Créé automatiquement avant restauration de {path.name}')
    with _BACKUP_LOCK, tempfile.TemporaryDirectory(prefix='pichat_restore_') as td, zipfile.ZipFile(path) as z:
        tmp=Path(td); db=tmp/'pichat.db'; db.write_bytes(z.read('database/pichat.db'))
        # Vérification SQLite
        with sqlite3.connect(db) as conn: conn.execute('PRAGMA integrity_check').fetchone()
        for suffix in ('-wal','-shm'):
            side=Path(str(DATABASE_PATH)+suffix); side.unlink(missing_ok=True)
        DATABASE_PATH.parent.mkdir(parents=True,exist_ok=True)
        staged=DATABASE_PATH.with_suffix('.db.restore_tmp'); shutil.copy2(db,staged); staged.replace(DATABASE_PATH)
        staged_uploads=tmp/'uploads'; staged_uploads.mkdir()
        for n in z.namelist():
            if n.startswith('uploads/') and not n.endswith('/'):
                rel=PurePosixPath(n).relative_to('uploads'); target=staged_uploads.joinpath(*rel.parts); target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(z.read(n))
        if UPLOADS_DIR.exists(): shutil.rmtree(UPLOADS_DIR)
        shutil.copytree(staged_uploads,UPLOADS_DIR)
        if 'config/friendly_url.json' in z.namelist(): FRIENDLY_URL_CONFIG.write_bytes(z.read('config/friendly_url.json'))
    return {'restored':path.name,'safety_backup':safety.name}
