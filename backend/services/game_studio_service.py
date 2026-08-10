from __future__ import annotations

import asyncio
import io
import json
import re
import secrets
import unicodedata
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

from database import get_db_cursor
from services.ai_service import _env_key, get_ai_settings


CHATGPT_URL = "https://chatgpt.com/"
MAX_ANSWER_CHARS = 120000
MAX_HTML_CHARS = 18000
MAX_CSS_CHARS = 22000
MAX_JS_CHARS = 36000
MAX_TOTAL_CHARS = 70000


class GameStudioError(Exception):
    pass


class _GameHTMLValidator(HTMLParser):
    FORBIDDEN_TAGS = {
        "script", "iframe", "frame", "frameset", "object", "embed", "applet",
        "link", "meta", "base", "form", "style",
        "video", "audio", "source", "track", "portal",
    }
    URL_ATTRIBUTES = {"src", "href", "xlink:href", "action", "formaction", "srcdoc"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.errors: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        low_tag = tag.lower()
        if low_tag in self.FORBIDDEN_TAGS:
            self.errors.append("Balise HTML refusée : <%s>." % low_tag)
        attr_map = {(name or "").lower(): (value or "") for name, value in attrs}
        if low_tag == "input":
            input_type = attr_map.get("type", "text").strip().lower()
            if input_type not in {"text", "number", "range", "checkbox", "radio", "color", "button"}:
                self.errors.append("Type de champ refusé : %s." % input_type)
        for name, value in attrs:
            low_name = (name or "").lower()
            if low_name.startswith("on"):
                self.errors.append("Les événements HTML intégrés sont refusés : %s." % low_name)
            if low_name in self.URL_ATTRIBUTES:
                self.errors.append("Les liens et ressources externes sont refusés : %s." % low_name)
            if value and "javascript:" in value.lower():
                self.errors.append("Lien JavaScript refusé.")

    def handle_startendtag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        self.handle_starttag(tag, attrs)


FORBIDDEN_JS_PATTERNS = [
    (r"\bfetch\s*\(", "accès réseau fetch"),
    (r"\bXMLHttpRequest\b", "accès réseau XMLHttpRequest"),
    (r"\bWebSocket\b", "WebSocket"),
    (r"\bEventSource\b", "EventSource"),
    (r"\bsendBeacon\b", "sendBeacon"),
    (r"\bimportScripts\b", "importScripts"),
    (r"\b(?:SharedWorker|Worker|ServiceWorker)\b", "worker"),
    (r"\bnavigator\s*\.\s*serviceWorker\b", "service worker"),
    (r"\bnavigator\s*\.\s*(?:clipboard|geolocation|credentials|share|usb|serial|hid|bluetooth)\b", "permission sensible du navigateur"),
    (r"\b(?:mediaDevices|getUserMedia|PaymentRequest|Notification|FileReader|showOpenFilePicker|showSaveFilePicker|webkitRequestFileSystem)\b", "API sensible du navigateur"),
    (r"\b(?:localStorage|sessionStorage|indexedDB)\b", "stockage du navigateur"),
    (r"\bdocument\s*\.\s*cookie\b", "cookies"),
    (r"\bwindow\s*\.\s*open\s*\(", "nouvelle fenêtre"),
    (r"\b(?:top|parent|opener)\s*\.", "accès à la page parente"),
    (r"\bpostMessage\s*\(", "communication externe"),
    (r"\beval\s*\(", "eval"),
    (r"\bFunction\s*\(", "constructeur Function"),
    (r"\bimport\s*\(", "import dynamique"),
    (r"\brequire\s*\(", "require"),
    (r"\bdocument\s*\.\s*write\s*\(", "document.write"),
    (r"\bWebAssembly\b", "WebAssembly"),
    (r"\bconstructor\s*\[", "construction dynamique"),
    (r"__proto__", "prototype dynamique"),
    (r"<\s*/?\s*script", "balise script injectée"),
    (r"while\s*\(\s*true\s*\)", "boucle infinie évidente"),
    (r"for\s*\(\s*;\s*;\s*\)", "boucle infinie évidente"),
    (r"\b(?:setTimeout|setInterval)\s*\(\s*['\"]", "code texte exécuté par minuterie"),
    (r"createElement\s*\(\s*['\"](?:script|iframe|object|embed|link)['\"]", "création d'une ressource active"),
]

FORBIDDEN_CSS_PATTERNS = [
    (r"@import", "@import"),
    (r"url\s*\(", "ressource externe CSS"),
    (r"expression\s*\(", "expression CSS"),
    (r"behavior\s*:", "behavior CSS"),
    (r"-moz-binding", "liaison CSS"),
    (r"<\s*/?\s*(?:style|script|iframe)", "balise injectée dans le CSS"),
]


def _slugify(value: str) -> str:
    normal = unicodedata.normalize("NFKD", value or "")
    ascii_value = normal.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_value).strip("-").lower()
    return slug[:48] or "mini-jeu"


def _extract_json(raw: str) -> Dict[str, Any]:
    text = (raw or "").strip()
    if len(text) > MAX_ANSWER_CHARS:
        raise GameStudioError("La réponse de ChatGPT est trop longue.")
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.I | re.S)
    if fenced:
        text = fenced.group(1).strip()
    else:
        first = text.find("{")
        last = text.rfind("}")
        if first < 0 or last <= first:
            raise GameStudioError("Aucun paquet JSON PiGame n'a été trouvé dans la réponse.")
        text = text[first:last + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise GameStudioError("Le paquet JSON est invalide près de la ligne %s." % error.lineno)
    if not isinstance(data, dict):
        raise GameStudioError("Le paquet PiGame doit être un objet JSON.")
    return data


def _normalise_package(data: Dict[str, Any], fallback_title: str = "") -> Dict[str, str]:
    html = data.get("html") or data.get("body") or ""
    css = data.get("css") or data.get("style") or ""
    javascript = data.get("javascript") or data.get("js") or data.get("script") or ""
    title = data.get("title") or fallback_title or "Mini-jeu"
    description = data.get("description") or "Mini-jeu créé avec PiGame Studio."
    icon = data.get("icon") or "🎮"
    return {
        "title": str(title).strip()[:80],
        "description": str(description).strip()[:240],
        "icon": str(icon).strip()[:12] or "🎮",
        "html": str(html).strip(),
        "css": str(css).strip(),
        "javascript": str(javascript).strip(),
    }


def validate_game_package(package: Dict[str, str]) -> Dict[str, Any]:
    html = package.get("html", "")
    css = package.get("css", "")
    javascript = package.get("javascript", "")
    if not package.get("title"):
        raise GameStudioError("Le jeu doit avoir un titre.")
    if not html or not javascript:
        raise GameStudioError("Le jeu doit contenir du HTML et du JavaScript.")
    if len(html) > MAX_HTML_CHARS:
        raise GameStudioError("Le HTML dépasse %s caractères." % MAX_HTML_CHARS)
    if len(css) > MAX_CSS_CHARS:
        raise GameStudioError("Le CSS dépasse %s caractères." % MAX_CSS_CHARS)
    if len(javascript) > MAX_JS_CHARS:
        raise GameStudioError("Le JavaScript dépasse %s caractères." % MAX_JS_CHARS)
    total = len(html) + len(css) + len(javascript)
    if total > MAX_TOTAL_CHARS:
        raise GameStudioError("Le jeu complet dépasse %s caractères." % MAX_TOTAL_CHARS)

    parser = _GameHTMLValidator()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        raise GameStudioError("Le HTML du jeu n'est pas valide.")
    if parser.errors:
        raise GameStudioError(parser.errors[0])

    for pattern, label in FORBIDDEN_CSS_PATTERNS:
        if re.search(pattern, css, re.I):
            raise GameStudioError("CSS refusé : %s." % label)
    for pattern, label in FORBIDDEN_JS_PATTERNS:
        if re.search(pattern, javascript, re.I):
            raise GameStudioError("JavaScript refusé : %s." % label)

    if re.search(r"\b(?:window\s*\.\s*)?location\b", javascript, re.I):
        raise GameStudioError("JavaScript refusé : navigation vers une autre page.")
    if re.search(r"\bhistory\s*\.", javascript, re.I):
        raise GameStudioError("JavaScript refusé : modification de l'historique du navigateur.")

    return {
        "safe": True,
        "html_chars": len(html),
        "css_chars": len(css),
        "javascript_chars": len(javascript),
        "total_chars": total,
        "checks": [
            "aucun accès réseau",
            "aucun stockage navigateur",
            "aucun accès à la page parente",
            "aucune ressource externe",
            "exécution isolée par iframe sandbox",
        ],
    }


def build_special_prompt(idea: str, title: str = "") -> str:
    idea = (idea or "").strip()
    title = (title or "").strip()
    if len(idea) < 8 or len(idea) > 3000:
        raise GameStudioError("Décris le jeu avec 8 à 3 000 caractères.")
    requested_title = title[:80] or "Choisis un titre court"
    return f"""Tu es le générateur officiel de mini-jeux de PiGame Studio pour PiChat.
Crée un petit jeu web complet, amusant, adapté au téléphone et à l'ordinateur.

IDÉE DE L'UTILISATEUR :
{idea}

TITRE SOUHAITÉ :
{requested_title}

CONTRAINTES ABSOLUES :
- Le jeu fonctionne hors ligne avec HTML, CSS et JavaScript natifs uniquement.
- Aucun framework, aucune bibliothèque, aucune image, police, son ou ressource externe.
- Aucun accès réseau : pas de fetch, XMLHttpRequest, WebSocket, EventSource ou sendBeacon.
- Aucun stockage : pas de cookies, localStorage, sessionStorage ou indexedDB.
- Aucun accès à window.parent, window.top, opener, postMessage, location ou history.
- Aucun eval, Function, import dynamique, worker, WebAssembly ou document.write.
- Pas de formulaire HTML ni de balises script dans le champ HTML.
- Les événements sont ajoutés dans le JavaScript avec addEventListener, jamais avec onclick dans le HTML.
- Le jeu doit avoir un bouton Rejouer, des instructions visibles et fonctionner au toucher.
- Le contenu doit rester familial, sans collecte de données, achat réel, publicité ni jeu d'argent.
- HTML maximum 18 000 caractères, CSS maximum 22 000, JavaScript maximum 36 000.

RÉPONSE OBLIGATOIRE :
Retourne uniquement un objet JSON valide, dans un unique bloc ```json```, sans explication avant ou après.
Utilise exactement cette structure :
{{
  "pichat_game": 1,
  "title": "Titre du jeu",
  "description": "Description courte",
  "icon": "🎮",
  "html": "HTML du contenu du jeu sans balise script/style",
  "css": "CSS du jeu",
  "javascript": "JavaScript du jeu"
}}

Le JSON doit être directement importable dans PiGame Studio. Échappe correctement les retours à la ligne et les guillemets."""


def get_settings() -> Dict[str, Any]:
    with get_db_cursor() as cursor:
        row = cursor.execute("SELECT * FROM game_studio_settings WHERE id=1").fetchone()
    if not row:
        return {
            "enabled": True,
            "direct_api_enabled": False,
            "require_admin_approval": True,
            "max_games_per_user": 8,
            "api_key_configured": bool(_env_key()),
        }
    result = dict(row)
    for key in ("enabled", "direct_api_enabled", "require_admin_approval"):
        result[key] = bool(result[key])
    result["api_key_configured"] = bool(_env_key())
    return result


def update_settings(enabled: bool, direct_api_enabled: bool, require_admin_approval: bool, max_games_per_user: int) -> Dict[str, Any]:
    maximum = max(1, min(int(max_games_per_user), 30))
    with get_db_cursor() as cursor:
        cursor.execute(
            """UPDATE game_studio_settings
               SET enabled=?,direct_api_enabled=?,require_admin_approval=?,max_games_per_user=?,updated_at=datetime('now')
               WHERE id=1""",
            (1 if enabled else 0, 1 if direct_api_enabled else 0, 1 if require_admin_approval else 0, maximum),
        )
    return get_settings()


def _serialise_game(row: Any, include_source: bool = False) -> Dict[str, Any]:
    game = dict(row)
    game["id"] = int(game["id"])
    game["plays"] = int(game.get("plays") or 0)
    game["owner_id"] = int(game["owner_id"])
    game["is_public"] = game.get("status") == "published"
    if include_source:
        try:
            game["safety"] = json.loads(game.get("safety_report") or "{}")
        except Exception:
            game["safety"] = {}
    else:
        for key in ("html_code", "css_code", "js_code", "source_prompt", "safety_report"):
            game.pop(key, None)
    return game


def _unique_slug(cursor: Any, title: str) -> str:
    base = _slugify(title)
    candidate = base
    for _ in range(20):
        if not cursor.execute("SELECT 1 FROM generated_games WHERE slug=?", (candidate,)).fetchone():
            return candidate
        candidate = "%s-%s" % (base[:40], secrets.token_hex(2))
    return "%s-%s" % (base[:36], secrets.token_hex(4))


def _save_game(owner_id: int, package: Dict[str, str], source_prompt: str, generation_mode: str) -> Dict[str, Any]:
    safety = validate_game_package(package)
    settings = get_settings()
    with get_db_cursor() as cursor:
        count = cursor.execute("SELECT COUNT(*) AS n FROM generated_games WHERE owner_id=?", (owner_id,)).fetchone()["n"]
        if int(count) >= int(settings["max_games_per_user"]):
            raise GameStudioError("Tu as atteint la limite de %s jeux. Supprime un brouillon avant d'en créer un autre." % settings["max_games_per_user"])
        slug = _unique_slug(cursor, package["title"])
        status = "draft"
        cursor.execute(
            """INSERT INTO generated_games
               (owner_id,title,slug,description,icon,source_prompt,generation_mode,html_code,css_code,js_code,status,safety_report)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                owner_id, package["title"], slug, package["description"], package["icon"],
                source_prompt[:3000], generation_mode, package["html"], package["css"],
                package["javascript"], status, json.dumps(safety, ensure_ascii=False),
            ),
        )
        row = cursor.execute(
            """SELECT g.*,u.username AS owner_username FROM generated_games g
               JOIN users u ON u.id=g.owner_id WHERE g.id=?""",
            (cursor.lastrowid,),
        ).fetchone()
    return _serialise_game(row, include_source=True)


def import_chatgpt_answer(owner_id: int, answer: str, idea: str = "", title: str = "") -> Dict[str, Any]:
    data = _extract_json(answer)
    if data.get("pichat_game") not in (1, "1", True):
        raise GameStudioError("La réponse n'est pas un paquet PiGame Studio reconnu.")
    package = _normalise_package(data, title)
    return _save_game(owner_id, package, idea, "chatgpt_web")



MAX_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_ZIP_FILES = 30
MAX_ZIP_UNCOMPRESSED = 3 * 1024 * 1024


def _decode_upload(content: bytes, label: str) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise GameStudioError("%s doit être encodé en UTF-8." % label)


def _package_from_full_html(text: str, fallback_title: str = "") -> Dict[str, str]:
    if re.search(r"<(?:iframe|object|embed|video|audio|form|base)\b", text, re.I):
        raise GameStudioError("Le fichier HTML contient une balise interdite.")
    if re.search(r"<(?:script|link)\b[^>]+(?:src|href)\s*=", text, re.I):
        raise GameStudioError("Le fichier HTML utilise une ressource externe. Intègre tout le code dans le fichier.")
    styles = re.findall(r"<style\b[^>]*>(.*?)</style>", text, re.I | re.S)
    scripts = re.findall(r"<script\b(?![^>]*\bsrc\s*=)[^>]*>(.*?)</script>", text, re.I | re.S)
    title_match = re.search(r"<title\b[^>]*>(.*?)</title>", text, re.I | re.S)
    body_match = re.search(r"<body\b[^>]*>(.*?)</body>", text, re.I | re.S)
    body = body_match.group(1) if body_match else text
    body = re.sub(r"<style\b[^>]*>.*?</style>", "", body, flags=re.I | re.S)
    body = re.sub(r"<script\b[^>]*>.*?</script>", "", body, flags=re.I | re.S)
    body = re.sub(r"<!doctype[^>]*>", "", body, flags=re.I)
    body = re.sub(r"</?(?:html|head|body)\b[^>]*>", "", body, flags=re.I)
    body = re.sub(r"<(?:meta|link)\b[^>]*>", "", body, flags=re.I)
    body = re.sub(r"</?title\b[^>]*>", "", body, flags=re.I)
    title = fallback_title or (re.sub(r"<[^>]+>", "", title_match.group(1)).strip() if title_match else "Mini-jeu importé")
    package = {
        "title": title[:80],
        "description": "Mini-jeu importé depuis un fichier HTML.",
        "icon": "🎮",
        "html": body.strip(),
        "css": "\n".join(styles).strip(),
        "javascript": "\n".join(scripts).strip(),
    }
    return package


def _safe_zip_files(content: bytes) -> Dict[str, bytes]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        raise GameStudioError("Le fichier ZIP est invalide.")
    infos = [info for info in archive.infolist() if not info.is_dir()]
    if len(infos) > MAX_ZIP_FILES:
        raise GameStudioError("Le ZIP contient trop de fichiers (maximum %s)." % MAX_ZIP_FILES)
    if sum(max(0, info.file_size) for info in infos) > MAX_ZIP_UNCOMPRESSED:
        raise GameStudioError("Le contenu décompressé du ZIP est trop volumineux.")
    result: Dict[str, bytes] = {}
    for info in infos:
        unix_mode = (info.external_attr >> 16) & 0xF000
        if unix_mode == 0xA000:
            raise GameStudioError("Les liens symboliques sont refusés dans le ZIP.")
        name = info.filename.replace("\\", "/").lstrip("/")
        parts = [part for part in name.split("/") if part not in ("", ".")]
        if not parts or ".." in parts:
            raise GameStudioError("Le ZIP contient un chemin de fichier dangereux.")
        if len(parts) > 4:
            raise GameStudioError("Le ZIP contient une arborescence trop profonde.")
        suffix = Path(parts[-1]).suffix.lower()
        if suffix not in {".json", ".html", ".htm", ".css", ".js", ".txt", ".md"}:
            raise GameStudioError("Type de fichier refusé dans le ZIP : %s." % suffix)
        result["/".join(parts).lower()] = archive.read(info)
    return result


def _find_zip_file(files: Dict[str, bytes], candidates: List[str], suffix: str = "") -> Optional[bytes]:
    for candidate in candidates:
        candidate = candidate.lower()
        if candidate in files:
            return files[candidate]
        for name, data in files.items():
            if name.endswith("/" + candidate):
                return data
    if suffix:
        for name, data in files.items():
            if name.endswith(suffix):
                return data
    return None


def _package_from_zip(content: bytes, fallback_title: str = "") -> Dict[str, str]:
    files = _safe_zip_files(content)
    manifest_bytes = _find_zip_file(files, ["pichat-game.json", "game.json", "manifest.json"])
    manifest: Dict[str, Any] = {}
    if manifest_bytes is not None:
        try:
            parsed = json.loads(_decode_upload(manifest_bytes, "Le manifeste"))
            if not isinstance(parsed, dict):
                raise ValueError
            manifest = parsed
        except (json.JSONDecodeError, ValueError):
            raise GameStudioError("Le manifeste JSON du ZIP est invalide.")
        if any(key in manifest for key in ("html", "body", "javascript", "js", "script")):
            return _normalise_package(manifest, fallback_title)

    html_name = str(manifest.get("html_file") or manifest.get("entry") or "index.html").replace("\\", "/").lstrip("/").lower()
    css_name = str(manifest.get("css_file") or "style.css").replace("\\", "/").lstrip("/").lower()
    js_name = str(manifest.get("javascript_file") or manifest.get("js_file") or "game.js").replace("\\", "/").lstrip("/").lower()
    html_bytes = files.get(html_name) or _find_zip_file(files, ["index.html", "game.html"], ".html")
    if html_bytes is None:
        raise GameStudioError("Le ZIP doit contenir index.html ou un manifeste indiquant le fichier HTML.")
    html_text = _decode_upload(html_bytes, "Le HTML")
    if re.search(r'(?:src|href)\s*=\s*[\'"]\s*(?:https?:|//|data:|javascript:)', html_text, re.I):
        raise GameStudioError("Le ZIP contient une ressource externe interdite.")
    # Dans un ZIP, les références locales vers style.css/game.js sont retirées :
    # PiChat lit directement les fichiers puis les injecte dans l'iframe isolée.
    html_text = re.sub(r"<link\b[^>]*>", "", html_text, flags=re.I)
    html_text = re.sub(r'<script\b[^>]*\bsrc\s*=\s*[\'"][^\'"]+[\'"][^>]*>\s*</script>', "", html_text, flags=re.I | re.S)
    inline = _package_from_full_html(html_text, fallback_title)
    css_bytes = files.get(css_name) or _find_zip_file(files, ["style.css", "game.css"], ".css")
    js_bytes = files.get(js_name) or _find_zip_file(files, ["game.js", "script.js", "app.js"], ".js")
    if css_bytes is not None:
        inline["css"] = (inline["css"] + "\n" + _decode_upload(css_bytes, "Le CSS")).strip()
    if js_bytes is not None:
        inline["javascript"] = (inline["javascript"] + "\n" + _decode_upload(js_bytes, "Le JavaScript")).strip()
    inline["title"] = str(manifest.get("title") or inline["title"] or fallback_title)[:80]
    inline["description"] = str(manifest.get("description") or "Mini-jeu importé depuis un ZIP.")[:240]
    inline["icon"] = str(manifest.get("icon") or "🎮")[:12]
    return inline


def import_game_file(owner_id: int, filename: str, content: bytes, fallback_title: str = "") -> Dict[str, Any]:
    if not content:
        raise GameStudioError("Le fichier est vide.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise GameStudioError("Le fichier dépasse 2 Mo.")
    suffix = Path(filename or "").suffix.lower()
    if suffix == ".json":
        data = _extract_json(_decode_upload(content, "Le JSON"))
        if data.get("pichat_game") not in (1, 2, "1", "2", True):
            raise GameStudioError("Le fichier JSON n'est pas un paquet PiGame reconnu.")
        package = _normalise_package(data, fallback_title)
        mode = "file_json"
    elif suffix in {".html", ".htm"}:
        package = _package_from_full_html(_decode_upload(content, "Le HTML"), fallback_title)
        mode = "file_html"
    elif suffix == ".zip":
        package = _package_from_zip(content, fallback_title)
        mode = "file_zip"
    elif suffix == ".css":
        css = _decode_upload(content, "Le CSS")
        package = {
            "title": (fallback_title or Path(filename).stem or "Jeu CSS importé")[:80],
            "description": "Brouillon PiGame importé depuis un fichier CSS.",
            "icon": "🎨",
            "html": "<main class='pigame-import-shell'><h1>PiGame CSS</h1><p>Ton style CSS est chargé dans cette sandbox.</p><button id='replay' type='button'>Rejouer</button></main>",
            "css": css,
            "javascript": "document.getElementById('replay').addEventListener('click',()=>{});",
        }
        mode = "file_css"
    elif suffix == ".js":
        javascript = _decode_upload(content, "Le JavaScript")
        package = {
            "title": (fallback_title or Path(filename).stem or "Jeu JavaScript importé")[:80],
            "description": "Brouillon PiGame importé depuis un fichier JavaScript.",
            "icon": "⚙️",
            "html": "<main id='game'><h1>PiGame JavaScript</h1><p id='instructions'>Le script importé s'exécute dans la sandbox PiGame.</p><button id='replay' type='button'>Rejouer</button></main>",
            "css": "#game{min-height:80vh;display:grid;place-content:center;gap:12px;text-align:center;padding:24px}",
            "javascript": javascript + "\n;document.getElementById('replay')?.addEventListener('click',()=>{});",
        }
        mode = "file_js"
    else:
        raise GameStudioError("Format refusé. Utilise un fichier .html, .css, .js, .json ou .zip.")
    return _save_game(owner_id, package, "Import de fichier : %s" % (filename or "jeu"), mode)


def build_game_template_zip() -> bytes:
    manifest = {
        "pichat_game": 2,
        "title": "Mon mini-jeu",
        "description": "Un exemple prêt à modifier puis à importer dans PiGame Studio.",
        "icon": "🎮",
        "html_file": "index.html",
        "css_file": "style.css",
        "javascript_file": "game.js",
    }
    html = """<main id="game"><h1>Mon mini-jeu</h1><p id="instructions">Appuie sur le bouton pour gagner un point.</p><strong id="score">Score : 0</strong><button id="play" type="button">Jouer</button><button id="replay" type="button">Rejouer</button></main>"""
    css = """#game{min-height:80vh;display:grid;place-content:center;gap:14px;text-align:center;padding:24px}button{border:0;border-radius:14px;padding:14px 20px;background:#5865f2;color:white;font-weight:800}#score{font-size:1.4rem}"""
    javascript = """const score=document.getElementById('score');const play=document.getElementById('play');const replay=document.getElementById('replay');let points=0;function render(){score.textContent='Score : '+points}play.addEventListener('click',()=>{points+=1;render()});replay.addEventListener('click',()=>{points=0;render()});render();"""
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("pichat-game.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.writestr("index.html", html)
        archive.writestr("style.css", css)
        archive.writestr("game.js", javascript)
        archive.writestr("LISEZ-MOI.txt", "Modifie les quatre fichiers, compresse-les en ZIP puis importe le ZIP dans PiGame Studio. N'ajoute aucune ressource Internet.")
    return output.getvalue()

def _openai_generate_sync(idea: str, title: str) -> str:
    settings = get_settings()
    if not settings["direct_api_enabled"]:
        raise GameStudioError("La génération automatique par API est désactivée par l'administrateur.")
    key = _env_key()
    if not key:
        raise GameStudioError("Aucune clé API OpenAI n'est configurée sur le serveur.")
    ai_settings = get_ai_settings()
    prompt = build_special_prompt(idea, title)
    payload = {
        "model": ai_settings.get("model") or "gpt-5.6",
        "instructions": "Suis exactement le format JSON demandé. Ne retourne aucun texte supplémentaire.",
        "input": prompt,
        "max_output_tokens": 5500,
    }
    req = urlrequest.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = ""
        try:
            detail = json.loads(error.read().decode("utf-8")).get("error", {}).get("message", "")
        except Exception:
            pass
        raise GameStudioError("OpenAI a refusé la génération%s" % ((" : " + detail[:240]) if detail else "."))
    except URLError:
        raise GameStudioError("Impossible de joindre l'API OpenAI.")
    texts: List[str] = []
    for item in data.get("output", []):
        if item.get("type") != "message":
            continue
        for part in item.get("content", []):
            if part.get("type") == "output_text" and part.get("text"):
                texts.append(part["text"])
    raw = "\n".join(texts).strip()
    if not raw:
        raise GameStudioError("OpenAI n'a renvoyé aucun paquet de jeu.")
    return raw


async def generate_with_api(owner_id: int, idea: str, title: str = "") -> Dict[str, Any]:
    raw = await asyncio.to_thread(_openai_generate_sync, idea, title)
    data = _extract_json(raw)
    package = _normalise_package(data, title)
    return _save_game(owner_id, package, idea, "openai_api")


def list_games(viewer_id: int, is_admin: bool = False) -> Dict[str, List[Dict[str, Any]]]:
    with get_db_cursor() as cursor:
        public_rows = cursor.execute(
            """SELECT g.id,g.owner_id,g.title,g.slug,g.description,g.icon,g.generation_mode,g.status,
                      g.created_at,g.updated_at,g.published_at,g.plays,u.username AS owner_username
               FROM generated_games g JOIN users u ON u.id=g.owner_id
               WHERE g.status='published' ORDER BY g.published_at DESC,g.id DESC LIMIT 100"""
        ).fetchall()
        my_rows = cursor.execute(
            """SELECT g.id,g.owner_id,g.title,g.slug,g.description,g.icon,g.generation_mode,g.status,
                      g.created_at,g.updated_at,g.published_at,g.review_note,g.plays,u.username AS owner_username
               FROM generated_games g JOIN users u ON u.id=g.owner_id
               WHERE g.owner_id=? ORDER BY g.id DESC LIMIT 50""",
            (viewer_id,),
        ).fetchall()
        pending_rows: List[Any] = []
        if is_admin:
            pending_rows = cursor.execute(
                """SELECT g.id,g.owner_id,g.title,g.slug,g.description,g.icon,g.generation_mode,g.status,
                          g.created_at,g.updated_at,g.review_note,g.plays,u.username AS owner_username
                   FROM generated_games g JOIN users u ON u.id=g.owner_id
                   WHERE g.status='pending' ORDER BY g.updated_at ASC,g.id ASC LIMIT 100"""
            ).fetchall()
    return {
        "published": [_serialise_game(row) for row in public_rows],
        "mine": [_serialise_game(row) for row in my_rows],
        "pending": [_serialise_game(row) for row in pending_rows],
    }


def get_game(game_id: int, viewer_id: int, is_admin: bool = False, count_play: bool = False) -> Dict[str, Any]:
    with get_db_cursor() as cursor:
        row = cursor.execute(
            """SELECT g.*,u.username AS owner_username FROM generated_games g
               JOIN users u ON u.id=g.owner_id WHERE g.id=?""",
            (game_id,),
        ).fetchone()
        if not row:
            raise GameStudioError("Jeu introuvable.")
        allowed = row["status"] == "published" or int(row["owner_id"]) == int(viewer_id) or is_admin
        if not allowed:
            raise GameStudioError("Ce jeu n'est pas accessible.")
        if count_play:
            cursor.execute("UPDATE generated_games SET plays=plays+1 WHERE id=?", (game_id,))
            cursor.execute(
                "INSERT INTO generated_game_plays(game_id,user_id) VALUES (?,?)",
                (game_id, viewer_id),
            )
    game = _serialise_game(row, include_source=True)
    game["document"] = build_sandbox_document(game)
    return game


def build_sandbox_document(game: Dict[str, Any]) -> str:
    csp = (
        "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
        "img-src data:; font-src 'none'; connect-src 'none'; media-src 'none'; "
        "object-src 'none'; frame-src 'none'; child-src 'none'; form-action 'none'; base-uri 'none'"
    )
    base_css = """
html,body{margin:0;min-height:100%;background:#11151f;color:#f4f6fb;font-family:system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;overflow:auto}
*{box-sizing:border-box}button{font:inherit;touch-action:manipulation}#pichat-game-root{min-height:100vh;padding:12px}
"""
    # Le bridge est fourni par PiChat et ne contient aucun token. Le code du
    # jeu garde connect-src='none' et ne peut pas appeler l'API directement.
    game_id = int(game.get("id") or 0)
    bridge = r"""
(()=>{
  const __post=window.parent.postMessage.bind(window.parent);
  let __context=Object.freeze({pseudo:'',pycoins:0,niveau:1,classement:[],succes:[]});
  const copy=()=>JSON.parse(JSON.stringify(__context));
  const api={
    profile:()=>copy(),
    pseudo:()=>__context.pseudo||'',
    pyCoins:()=>Number(__context.pycoins||0),
    niveau:()=>Number(__context.niveau||1),
    classement:()=>copy().classement||[],
    succes:()=>copy().succes||[],
    submitScore:(score)=>{const n=Math.trunc(Number(score));if(Number.isFinite(n))__post({__pigame:1,type:'score',game_id:__GAME__,score:Math.max(-1000000000,Math.min(1000000000,n))},'*')},
    unlockAchievement:(key,title='')=>{const k=String(key||'').slice(0,48);if(k)__post({__pigame:1,type:'achievement',game_id:__GAME__,key:k,title:String(title||'').slice(0,80)},'*')},
    refresh:()=>__post({__pigame:1,type:'refresh',game_id:__GAME__},'*')
  };
  Object.freeze(api);
  Object.defineProperty(window,'PiGame',{value:api,writable:false,configurable:false,enumerable:true});
  window.addEventListener('message',(event)=>{
    const data=event.data;
    if(!data||data.__pigame_context!==1||Number(data.game_id)!==__GAME__)return;
    const safe=data.context||{};
    __context=Object.freeze({
      pseudo:String(safe.pseudo||'').slice(0,64),
      pycoins:Number(safe.pycoins||0),
      niveau:Number(safe.niveau||1),
      classement:Array.isArray(safe.classement)?safe.classement.slice(0,20):[],
      succes:Array.isArray(safe.succes)?safe.succes.slice(0,100):[]
    });
    window.dispatchEvent(new CustomEvent('pigame:ready',{detail:copy()}));
  });
  __post({__pigame:1,type:'ready',game_id:__GAME__},'*');
})();
""".replace("__GAME__", str(game_id))
    return (
        "<!doctype html><html lang='fr'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1,viewport-fit=cover'>"
        "<meta http-equiv='Content-Security-Policy' content=\"%s\">"
        "<style>%s\n%s</style></head><body><div id='pichat-game-root'>%s</div>"
        "<script>\"use strict\";\n%s\n%s\n</script></body></html>"
        % (csp, base_css, game.get("css_code", ""), game.get("html_code", ""), bridge, game.get("js_code", ""))
    )


def _require_game_access(cursor: Any, game_id: int, user_id: int, is_admin: bool = False) -> Any:
    row = cursor.execute("SELECT id,owner_id,status FROM generated_games WHERE id=?", (game_id,)).fetchone()
    if not row:
        raise GameStudioError("Jeu introuvable.")
    if row["status"] != "published" and int(row["owner_id"]) != int(user_id) and not is_admin:
        raise GameStudioError("Ce jeu n'est pas accessible.")
    return row


def get_pigame_context(game_id: int, user_id: int, is_admin: bool = False) -> Dict[str, Any]:
    with get_db_cursor() as cursor:
        _require_game_access(cursor, game_id, user_id, is_admin)
        user = cursor.execute("SELECT username,xp,coins FROM users WHERE id=?", (user_id,)).fetchone()
        leaders = cursor.execute(
            """SELECT l.score,u.username FROM game_leaderboard_entries l
               JOIN users u ON u.id=l.user_id WHERE l.game_id=?
               ORDER BY l.score DESC,l.updated_at ASC LIMIT 20""",
            (game_id,),
        ).fetchall()
        achievements = cursor.execute(
            "SELECT achievement_key,title,unlocked_at FROM game_achievements WHERE game_id=? AND user_id=? ORDER BY unlocked_at",
            (game_id, user_id),
        ).fetchall()
    xp = int(user["xp"] or 0) if user else 0
    return {
        "pseudo": user["username"] if user else "",
        "pycoins": int(user["coins"] or 0) if user else 0,
        "niveau": 1 + xp // 100,
        "classement": [{"pseudo": r["username"], "score": int(r["score"])} for r in leaders],
        "succes": [{"key": r["achievement_key"], "title": r["title"], "unlocked_at": r["unlocked_at"]} for r in achievements],
    }


def submit_pigame_score(game_id: int, user_id: int, score: int, is_admin: bool = False) -> Dict[str, Any]:
    score = max(-1_000_000_000, min(1_000_000_000, int(score)))
    with get_db_cursor() as cursor:
        _require_game_access(cursor, game_id, user_id, is_admin)
        existing = cursor.execute(
            "SELECT score FROM game_leaderboard_entries WHERE game_id=? AND user_id=?",
            (game_id, user_id),
        ).fetchone()
        best = max(score, int(existing["score"])) if existing else score
        cursor.execute(
            """INSERT INTO game_leaderboard_entries(game_id,user_id,score,updated_at)
               VALUES (?,?,?,datetime('now'))
               ON CONFLICT(game_id,user_id) DO UPDATE SET score=excluded.score,updated_at=excluded.updated_at""",
            (game_id, user_id, best),
        )
    return {"ok": True, "score": best, "context": get_pigame_context(game_id, user_id, is_admin)}


def unlock_pigame_achievement(game_id: int, user_id: int, key: str, title: str = "", is_admin: bool = False) -> Dict[str, Any]:
    clean_key = re.sub(r"[^a-zA-Z0-9_.:-]+", "-", (key or "").strip())[:48]
    if not clean_key:
        raise GameStudioError("Identifiant de succès invalide.")
    clean_title = (title or clean_key.replace("-", " ").title()).strip()[:80]
    with get_db_cursor() as cursor:
        _require_game_access(cursor, game_id, user_id, is_admin)
        cursor.execute(
            """INSERT INTO game_achievements(game_id,user_id,achievement_key,title) VALUES (?,?,?,?)
               ON CONFLICT(game_id,user_id,achievement_key) DO NOTHING""",
            (game_id, user_id, clean_key, clean_title),
        )
    return {"ok": True, "context": get_pigame_context(game_id, user_id, is_admin)}

def _sync_creator_badges(cursor: Any, owner_id: int) -> None:
    badges = [
        ("game-creator", "Créateur de jeux", "A publié son premier jeu PiGame Studio", "🧪", "#9d62ff", "studio", 1),
        ("game-studio-master", "Maître du Studio", "A publié au moins trois jeux PiGame Studio", "🎮", "#f0b232", "studio", 1),
    ]
    for badge in badges:
        cursor.execute(
            """INSERT OR IGNORE INTO badge_definitions
               (code,name,description,icon,color,category,is_system,is_active)
               VALUES (?,?,?,?,?,?,?,1)""", badge
        )
    published = int(cursor.execute(
        "SELECT COUNT(*) AS n FROM generated_games WHERE owner_id=? AND status='published'",
        (owner_id,),
    ).fetchone()["n"] or 0)
    codes = ["game-creator"] if published >= 1 else []
    if published >= 3:
        codes.append("game-studio-master")
    for code in codes:
        badge = cursor.execute("SELECT id FROM badge_definitions WHERE code=?", (code,)).fetchone()
        if badge:
            cursor.execute(
                """INSERT OR IGNORE INTO user_badges
                   (user_id,badge_id,awarded_by,reason,showcased,display_order)
                   VALUES (?,?,NULL,?,1,0)""",
                (owner_id, badge["id"], "Jeu publié dans PiGame Studio"),
            )


def submit_game(game_id: int, owner_id: int, is_admin: bool = False) -> Dict[str, Any]:
    settings = get_settings()
    with get_db_cursor() as cursor:
        row = cursor.execute("SELECT owner_id,status FROM generated_games WHERE id=?", (game_id,)).fetchone()
        if not row:
            raise GameStudioError("Jeu introuvable.")
        if int(row["owner_id"]) != int(owner_id) and not is_admin:
            raise GameStudioError("Tu ne peux pas envoyer ce jeu en validation.")
        if row["status"] not in ("draft", "rejected"):
            raise GameStudioError("Ce jeu ne peut pas être envoyé dans son état actuel.")
        if settings["require_admin_approval"] and not is_admin:
            status = "pending"
            published_at = None
        else:
            status = "published"
            published_at = "datetime('now')"
        if published_at:
            cursor.execute(
                "UPDATE generated_games SET status=?,published_at=datetime('now'),review_note='',updated_at=datetime('now') WHERE id=?",
                (status, game_id),
            )
        else:
            cursor.execute(
                "UPDATE generated_games SET status=?,review_note='',updated_at=datetime('now') WHERE id=?",
                (status, game_id),
            )
        if status == "published":
            _sync_creator_badges(cursor, int(row["owner_id"]))
        updated = cursor.execute(
            """SELECT g.*,u.username AS owner_username FROM generated_games g
               JOIN users u ON u.id=g.owner_id WHERE g.id=?""", (game_id,)
        ).fetchone()
    return _serialise_game(updated, include_source=True)


def review_game(game_id: int, admin_id: int, approve: bool, note: str = "") -> Dict[str, Any]:
    with get_db_cursor() as cursor:
        row = cursor.execute("SELECT status,owner_id FROM generated_games WHERE id=?", (game_id,)).fetchone()
        if not row:
            raise GameStudioError("Jeu introuvable.")
        if approve:
            cursor.execute(
                """UPDATE generated_games SET status='published',reviewed_by=?,review_note=?,
                   published_at=datetime('now'),updated_at=datetime('now') WHERE id=?""",
                (admin_id, (note or "").strip()[:300], game_id),
            )
        else:
            cursor.execute(
                """UPDATE generated_games SET status='rejected',reviewed_by=?,review_note=?,
                   published_at=NULL,updated_at=datetime('now') WHERE id=?""",
                (admin_id, (note or "").strip()[:300], game_id),
            )
        if approve:
            _sync_creator_badges(cursor, int(row["owner_id"]))
        updated = cursor.execute(
            """SELECT g.*,u.username AS owner_username FROM generated_games g
               JOIN users u ON u.id=g.owner_id WHERE g.id=?""", (game_id,)
        ).fetchone()
    return _serialise_game(updated, include_source=True)


def delete_game(game_id: int, user_id: int, is_admin: bool = False) -> None:
    with get_db_cursor() as cursor:
        row = cursor.execute("SELECT owner_id FROM generated_games WHERE id=?", (game_id,)).fetchone()
        if not row:
            raise GameStudioError("Jeu introuvable.")
        if int(row["owner_id"]) != int(user_id) and not is_admin:
            raise GameStudioError("Tu ne peux pas supprimer ce jeu.")
        cursor.execute("DELETE FROM generated_games WHERE id=?", (game_id,))
