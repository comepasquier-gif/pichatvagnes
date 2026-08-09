#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / "venv"
PY = VENV / "bin" / "python"
VERSION = "3.3.0"
PROTECTED = {"database", "uploads", "backups", "venv", ".env", "logs", "runtime", "deployment"}


def run(cmd, check=True, cwd=ROOT, env=None):
    cmd = [str(x) for x in cmd]
    print("›", " ".join(cmd))
    return subprocess.run(cmd, cwd=cwd, check=check, env=env)


def system_python():
    if sys.version_info < (3, 9):
        raise SystemExit("PiChat 2.1 nécessite Python 3.9 ou plus récent.")
    return Path(sys.executable)


def venv_healthy():
    if not PY.exists():
        return False
    result = subprocess.run([str(PY), "-c", "import sys;print(sys.version_info[:2])"], capture_output=True, text=True)
    return result.returncode == 0


def ensure(repair=False):
    system_python()
    if repair and VENV.exists() and not venv_healthy():
        print("Environnement Python endommagé : reconstruction…")
        shutil.rmtree(VENV, ignore_errors=True)
    if not VENV.exists():
        run([sys.executable, "-m", "venv", VENV])
    if not venv_healthy():
        raise SystemExit("Le venv PiChat ne démarre pas. Relance : python3 pichat.py repair --rebuild")
    run([PY, "-m", "pip", "install", "--upgrade", "pip"], check=False)
    run([PY, "-m", "pip", "install", "-r", ROOT / "requirements.txt"])


def local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def load_env_file(path: Path):
    env = os.environ.copy()
    if path.exists():
        for raw in path.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw or raw.startswith("#") or "=" not in raw:
                continue
            key, value = raw.split("=", 1)
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def start(mode="local"):
    ensure()
    host = "127.0.0.1"
    addr = "localhost"
    env = os.environ.copy()
    extra = []
    if mode == "network":
        host = "0.0.0.0"
        addr = local_ip()
    elif mode == "internet":
        host = "127.0.0.1"
        env = load_env_file(ROOT / "deployment" / "pichat.production.env")
        env["PICHAT_INTERNET_MODE"] = "1"
        extra = ["--proxy-headers", "--forwarded-allow-ips", "*"]
        addr = env.get("PICHAT_PUBLIC_URL", "http://127.0.0.1:8000")
        if not addr.startswith("http"):
            addr = "http://127.0.0.1:8000"
    shown = addr if "://" in addr else f"http://{addr}:8000"
    print(f"\nPiChat {VERSION} : {shown}\nCtrl+C pour arrêter.\n")
    os.chdir(ROOT / "backend")
    os.execve(
        str(PY),
        [str(PY), "-m", "uvicorn", "main:app", "--host", host, "--port", "8000", *extra],
        env,
    )


def diagnostic():
    print(f"PiChat {VERSION} — diagnostic Mac")
    print("Projet :", ROOT)
    print("Python système :", sys.version.split()[0])
    print("venv :", "OK" if venv_healthy() else "ABSENT / ENDOMMAGÉ")
    print("Base :", "OK" if (ROOT / "database" / "pichat.db").exists() else "sera créée au démarrage")
    print("Espace disque :", round(shutil.disk_usage(ROOT).free / 1024**3, 1), "Go libres")
    print("IP locale :", local_ip())
    problems = []
    try:
        import py_compile
        for file in (ROOT / "backend").rglob("*.py"):
            py_compile.compile(str(file), doraise=True)
        print("Syntaxe Python : OK")
    except Exception as exc:
        problems.append(str(exc))
        print("Syntaxe Python : ERREUR", exc)
    if PY.exists():
        result = subprocess.run([str(PY), "-c", "import fastapi,uvicorn,bcrypt,qrcode;print('Dépendances : OK')"], capture_output=True, text=True)
        print(result.stdout.strip() or "Dépendances : ERREUR")
        if result.returncode:
            problems.append(result.stderr.strip())
    return not problems


def repair(rebuild=False):
    print("Réparation PiChat 3.3.0 Oracle Free…")
    if rebuild and VENV.exists():
        shutil.rmtree(VENV, ignore_errors=True)
    ensure(repair=True)
    (ROOT / "database").mkdir(exist_ok=True)
    (ROOT / "uploads").mkdir(exist_ok=True)
    (ROOT / "backups").mkdir(exist_ok=True)
    (ROOT / "logs").mkdir(exist_ok=True)
    run([PY, "-c", "import sys;sys.path.insert(0,'backend');from database import init_database;init_database();print('Migration base : OK')"])
    diagnostic()
    print("Réparation terminée.")


def prepare_internet(url: str):
    ensure()
    if not url.startswith("https://"):
        raise SystemExit("Utilise une URL HTTPS, par exemple https://chat.mondomaine.fr")
    code = (
        "import sys;sys.path.insert(0,'backend');"
        "from database import init_database;init_database();"
        "from services.deployment_service import update_settings,write_deployment_files;"
        f"update_settings({{'public_url':{url!r},'allowed_hosts':{url.split('://',1)[1].split('/',1)[0]!r}+',localhost,127.0.0.1','proxy_headers':True,'https_enabled':True,'internet_ready':True}});"
        f"print(write_deployment_files({url!r})['directory'])"
    )
    run([PY, "-c", code])
    print("\nFichiers Internet générés dans PiChat/deployment/.")
    print("Installe Caddy puis lance : sudo caddy run --config deployment/Caddyfile")
    print("Dans un autre Terminal : python3 pichat.py internet")



def cloud_command(arguments):
    ensure()
    action = arguments[0] if arguments else "start"
    code_prefix = "import sys;sys.path.insert(0,'backend');from services.cloud_runtime_service import "
    if action == "install":
        run([PY, "-c", code_prefix + "install_cloudflared;print(install_cloudflared())"]); return
    if action == "status":
        run([PY, "-c", code_prefix + "status;print(status())"]); return
    if action == "stop":
        run([PY, "-c", code_prefix + "stop_tunnel;print(stop_tunnel())"]); return
    if action == "quick":
        run([PY, "-c", code_prefix + "install_cloudflared,start_quick_tunnel,status;"
             "s=status();install_cloudflared() if not s.get('installed') else None;"
             "s=status();print(s if s.get('running') else start_quick_tunnel())"]); return
    if action not in {"start", "permanent"}:
        raise SystemExit("Usage : python3 pichat.py cloud [start|install|quick|permanent|status|stop]")
    mode = "permanent" if action == "permanent" else "auto"
    code = (
        code_prefix + "status,install_cloudflared,start_quick_tunnel,start_permanent_tunnel;"
        "s=status();install_cloudflared() if not s.get('installed') else None;"
        + ("s=status();r=(s if s.get('running') else start_permanent_tunnel());" if mode == "permanent" else "s=status();r=(s if s.get('running') else (start_permanent_tunnel() if s.get('token_configured') else start_quick_tunnel()));")
        + "print('URL publique :',r.get('public_url',''))"
    )
    run([PY, "-c", code])
    start("internet")


def backup():
    run([sys.executable, ROOT / "backup.py"])


def update_from_zip(zip_path: str):
    package = Path(zip_path).expanduser().resolve()
    if not package.exists() or not zipfile.is_zipfile(package):
        raise SystemExit("ZIP de mise à jour introuvable ou invalide.")
    print("1/5 Backup de sécurité")
    backup()
    with tempfile.TemporaryDirectory(prefix="pichat-update-") as tmp:
        tmp_path = Path(tmp)
        with zipfile.ZipFile(package) as zf:
            zf.extractall(tmp_path)
        candidates = [p for p in tmp_path.rglob("PiChat") if (p / "backend" / "main.py").exists()]
        if not candidates and (tmp_path / "backend" / "main.py").exists():
            candidates = [tmp_path]
        if not candidates:
            raise SystemExit("Le ZIP ne contient pas un dossier PiChat valide.")
        source = candidates[0]
        print("2/5 Validation du paquet")
        for required in ("backend/main.py", "backend/database.py", "requirements.txt"):
            if not (source / required).exists():
                raise SystemExit(f"Fichier requis manquant : {required}")
        print("3/5 Copie des fichiers applicatifs")
        for child in source.iterdir():
            if child.name in PROTECTED:
                continue
            target = ROOT / child.name
            if child.is_dir():
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(child, target)
            else:
                shutil.copy2(child, target)
    print("4/5 Dépendances et migration")
    repair(False)
    print("5/5 Mise à jour terminée. L'application installée reste la même.")


def main():
    ap = argparse.ArgumentParser(description="Centre de gestion PiChat 3.3.0 Oracle Free")
    ap.add_argument(
        "action",
        choices=[
            "install", "repair", "start", "network", "internet", "prepare-internet",
            "admin", "user", "moderator", "test-pack", "packs", "cloud", "railway", "oracle", "pro", "launch", "backup", "restore", "doctor", "update", "version",
        ],
    )
    ap.add_argument("args", nargs="*")
    ap.add_argument("--rebuild", action="store_true")
    args, unknown = ap.parse_known_args()
    if unknown and args.action != "test-pack":
        ap.error("arguments inconnus : %s" % " ".join(unknown))
    if args.action == "install":
        ensure()
        repair(False)
    elif args.action == "repair":
        repair(args.rebuild)
    elif args.action == "start":
        start("local")
    elif args.action == "network":
        start("network")
    elif args.action == "internet":
        start("internet")
    elif args.action == "prepare-internet":
        if not args.args:
            raise SystemExit("Exemple : python3 pichat.py prepare-internet https://chat.mondomaine.fr")
        prepare_internet(args.args[0])
    elif args.action == "admin":
        ensure(); run([PY, ROOT / "create_admin.py", *args.args])
    elif args.action == "user":
        ensure(); run([PY, ROOT / "create_user.py", *args.args])
    elif args.action == "moderator":
        ensure(); run([PY, ROOT / "set_moderator.py", *args.args])
    elif args.action == "test-pack":
        ensure()
        if not args.args:
            raise SystemExit("Exemples : python3 pichat.py test-pack create --accounts 20 | python3 pichat.py test-pack clean | python3 pichat.py test-pack status")
        run([PY, ROOT / "test_pack.py", *args.args, *unknown])
    elif args.action == "packs":
        ensure()
        pack_args = args.args or ["status"]
        run([PY, ROOT / "final_packs.py", *pack_args])
    elif args.action == "cloud":
        cloud_command(args.args)
    elif args.action == "railway":
        ensure()
        action = args.args[0] if args.args else "status"
        if action == "status":
            code = "import sys,json;sys.path.insert(0,'backend');from database import init_database;init_database();from services.railway_service import overview;print(json.dumps(overview(),ensure_ascii=False,indent=2))"
            run([PY, "-c", code])
        elif action == "bundle":
            code = "import sys;sys.path.insert(0,'backend');from database import init_database;init_database();from services.railway_service import create_deploy_bundle;print(create_deploy_bundle())"
            run([PY, "-c", code])
        elif action == "variables":
            code = "import sys;sys.path.insert(0,'backend');from services.railway_service import variables_text;print(variables_text())"
            run([PY, "-c", code])
        else:
            raise SystemExit("Usage : python3 pichat.py railway [status|bundle|variables]")
    elif args.action == "oracle":
        action = args.args[0] if args.args else "help"
        if action == "help":
            print("PiChat Oracle Free :")
            print("  python3 pichat.py oracle info")
            print("  python3 pichat.py oracle bundle")
        elif action == "info":
            print("Déploiement Oracle : voir oracle/GUIDE_ORACLE_FREE.html")
            print("Installation serveur : sudo bash oracle/install_oracle.sh")
        elif action == "bundle":
            out = ROOT / "deployment" / "PiChat_Oracle_Server.zip"
            out.parent.mkdir(parents=True, exist_ok=True)
            protected = {"venv", "database", "uploads", "backups", "logs", "runtime", "deployment", ".env"}
            with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in ROOT.rglob("*"):
                    if not f.is_file():
                        continue
                    rel = f.relative_to(ROOT)
                    if any(part in protected for part in rel.parts):
                        continue
                    if "__pycache__" in rel.parts or f.suffix in {".pyc", ".pyo"}:
                        continue
                    zf.write(f, Path("PiChat") / rel)
            print(out)
        else:
            raise SystemExit("Usage : python3 pichat.py oracle [help|info|bundle]")
    elif args.action == "pro":
        ensure()
        action = args.args[0] if args.args else "status"
        if action == "status":
            code = "import sys,json;sys.path.insert(0,'backend');from database import init_database;init_database();from services.pro_center_service import overview;print(json.dumps(overview(),ensure_ascii=False,indent=2))"
            run([PY, "-c", code])
        elif action == "bundle":
            code = "import sys;sys.path.insert(0,'backend');from database import init_database;init_database();from services.pro_center_service import create_support_bundle;print(create_support_bundle())"
            run([PY, "-c", code])
        else:
            raise SystemExit("Usage : python3 pichat.py pro [status|bundle]")
    elif args.action == "launch":
        ensure()
        action = args.args[0] if args.args else "status"
        if action == "status":
            code = "import sys,json;sys.path.insert(0,'backend');from database import init_database;init_database();from services.launch31_service import overview;d=overview();print('PiChat 3.2 — score %s/100 — %s' % (d['score'],'PRÊT' if d['ready'] else 'À VÉRIFIER'));print(json.dumps(d['recommendations'],ensure_ascii=False,indent=2))"
            run([PY, "-c", code])
        elif action == "prepare":
            code = "import sys,json;sys.path.insert(0,'backend');from database import init_database;init_database();from services.launch31_service import prepare_launch;d=prepare_launch();print('Backup:',d.get('backup_created'));print('Score:',str(d.get('score'))+'/100');print('Prêt:',d.get('ready'))"
            run([PY, "-c", code])
        else:
            raise SystemExit("Usage : python3 pichat.py launch [status|prepare]")
    elif args.action == "backup":
        backup()
    elif args.action == "restore":
        if not args.args:
            raise SystemExit("Indique le ZIP à restaurer.")
        run([sys.executable, ROOT / "restore_backup.py", args.args[0]])
    elif args.action == "doctor":
        diagnostic()
    elif args.action == "update":
        if not args.args:
            raise SystemExit("Indique le ZIP de mise à jour.")
        update_from_zip(args.args[0])
    else:
        print(VERSION)


if __name__ == "__main__":
    main()
