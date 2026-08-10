from __future__ import annotations

import ast
import asyncio
import json
import re
import secrets
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

from database import get_db_cursor
from security import hash_password
from services.ai_service import get_ai_settings, _env_key
from services.message_service import save_message
from services.pycoin_service import debit, credit, PyCoinError, get_economy_settings

CODE_BOT_NAME = "PiCode"
ALLOWED_IMPORTS = {
    "math", "random", "statistics", "datetime", "collections", "itertools", "functools", "decimal", "fractions"
}
FORBIDDEN_CALLS = {
    "open", "exec", "eval", "compile", "__import__", "globals", "locals", "vars", "breakpoint"
}
FORBIDDEN_ATTRIBUTES = {
    "system", "popen", "spawn", "fork", "remove", "unlink", "rmdir", "rename", "replace",
    "walk", "listdir", "connect", "urlopen", "request", "chmod", "chown", "kill"
}


class CodeLabError(Exception):
    pass


def ensure_code_bot() -> int:
    with get_db_cursor() as cursor:
        row = cursor.execute("SELECT id FROM users WHERE username=?", (CODE_BOT_NAME,)).fetchone()
        if row:
            return int(row["id"])
        cursor.execute(
            """INSERT INTO users
               (username,password_hash,is_bot,status_message,grade_title,grade_color,profile_color)
               VALUES (?,?,1,?,?,?,?)""",
            (CODE_BOT_NAME, hash_password(secrets.token_urlsafe(32)), "Atelier Python sécurisé", "CODE IA", "#22d3a6", "#22d3a6"),
        )
        return int(cursor.lastrowid)


def _extract_code(text: str) -> str:
    match = re.search(r"```(?:python)?\s*(.*?)```", text, re.I | re.S)
    code = match.group(1) if match else text
    return code.strip()


def validate_python_code(code: str) -> dict:
    if not code or len(code) > 7000:
        raise CodeLabError("Le code généré est vide ou trop long.")
    if len(code.splitlines()) > 140:
        raise CodeLabError("Le mini-code dépasse 140 lignes.")
    try:
        tree = ast.parse(code)
    except SyntaxError as error:
        raise CodeLabError(f"Le code généré contient une erreur de syntaxe : ligne {error.lineno}.")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            else:
                names = [(node.module or "").split(".")[0]]
            for name in names:
                if name and name not in ALLOWED_IMPORTS:
                    raise CodeLabError(f"Import refusé dans PiCode : {name}.")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALLS:
                raise CodeLabError(f"Fonction refusée dans PiCode : {node.func.id}.")
            if isinstance(node.func, ast.Attribute) and node.func.attr in FORBIDDEN_ATTRIBUTES:
                raise CodeLabError(f"Action système ou réseau refusée : {node.func.attr}.")
        if isinstance(node, (ast.With, ast.AsyncWith)):
            raise CodeLabError("Les gestionnaires de fichiers/contexte ne sont pas autorisés dans les mini-codes.")
    return {"safe": True, "lines": len(code.splitlines())}


def _local_code(prompt: str) -> tuple[str, str]:
    low = prompt.lower()
    if "dé" in low or "dice" in low or "aléatoire" in low:
        code = '''import random\n\nfaces = 20\nresultat = random.randint(1, faces)\nprint(f"Résultat du dé : {resultat}")'''
        explanation = "Un petit lanceur de dé utilisant uniquement le module standard random."
    elif "calcul" in low or "calculatrice" in low:
        code = '''def calculer(a, operateur, b):\n    if operateur == "+":\n        return a + b\n    if operateur == "-":\n        return a - b\n    if operateur == "*":\n        return a * b\n    if operateur == "/":\n        return "Division impossible" if b == 0 else a / b\n    return "Opérateur inconnu"\n\nprint(calculer(12, "*", 3))'''
        explanation = "Une calculatrice simple organisée autour d'une fonction réutilisable."
    elif "quiz" in low or "question" in low:
        code = '''questions = [\n    ("Quelle est la capitale de la France ?", "Paris"),\n    ("Combien font 7 x 8 ?", "56"),\n]\n\nscore = 0\nfor question, bonne_reponse in questions:\n    print(question)\n    reponse = input("> ").strip()\n    if reponse.lower() == bonne_reponse.lower():\n        score += 1\n        print("Bonne réponse !")\n    else:\n        print(f"Réponse attendue : {bonne_reponse}")\n\nprint(f"Score : {score}/{len(questions)}")'''
        explanation = "Un mini-quiz modifiable avec une liste de questions et un compteur de score."
    else:
        code = '''def afficher_message(nom, nombre=3):\n    for numero in range(1, nombre + 1):\n        print(f"{numero}. Bonjour {nom} !")\n\nafficher_message("PiChat")'''
        explanation = "Exemple pédagogique avec une fonction, une boucle et des paramètres. Active OpenAI dans l'admin pour générer un code vraiment adapté au prompt."
    return code, explanation


def _openai_sync(prompt: str, title: str, user: dict, settings: dict) -> tuple[str, str]:
    key = _env_key()
    if not key:
        raise CodeLabError("Aucune clé OpenAI configurée.")
    instructions = """Tu es PiCode, générateur de mini-programmes Python pédagogiques pour des élèves.
Retourne exactement un bloc ```python ... ``` puis une explication de 2 à 5 phrases.
Contraintes absolues : code court, bibliothèque standard seulement, aucun accès réseau, aucun accès fichier,
aucune commande système, aucun subprocess, aucune collecte de données, aucun eval/exec, aucun code caché.
Le programme doit être compréhensible, commenté avec modération et fonctionner avec Python 3.9+."""
    payload = {
        "model": settings.get("model") or "gpt-5.6",
        "instructions": instructions,
        "input": f"Titre souhaité : {title or 'Mini-code Python'}\nClasse : {user.get('class_code') or '-'}\nDemande : {prompt}",
        "max_output_tokens": 900,
    }
    req = urlrequest.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=45) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise CodeLabError(f"OpenAI a refusé la génération ({error.code}).")
    except URLError:
        raise CodeLabError("Impossible de joindre le service IA.")
    texts = []
    for item in data.get("output", []):
        if item.get("type") != "message":
            continue
        for part in item.get("content", []):
            if part.get("type") == "output_text" and part.get("text"):
                texts.append(part["text"])
    raw = "\n".join(texts).strip()
    if not raw:
        raise CodeLabError("L'IA n'a renvoyé aucun code.")
    code = _extract_code(raw)
    explanation = re.sub(r"```(?:python)?\s*.*?```", "", raw, flags=re.I | re.S).strip()
    return code, explanation[:1200] or "Mini-code généré par PiCode."


async def create_code_message(room_id: int, user: dict, prompt: str, title: str = "") -> dict:
    prompt = (prompt or "").strip()
    title = (title or "Mini-code Python").strip()[:80]
    if len(prompt) < 3 or len(prompt) > 2000:
        raise CodeLabError("Le prompt doit contenir entre 3 et 2 000 caractères.")
    code_cost = get_economy_settings()["code_cost"]
    try:
        if code_cost > 0:
            debit(user["id"], code_cost, "code_generation", f"PiCode : {title}")
    except PyCoinError as error:
        raise CodeLabError(str(error))
    settings = get_ai_settings()
    provider = "local"
    try:
        if settings.get("enabled") and settings.get("provider") == "openai":
            code, explanation = await asyncio.to_thread(_openai_sync, prompt, title, user, settings)
            provider = "openai"
        else:
            code, explanation = _local_code(prompt)
        safety = validate_python_code(code)
    except Exception:
        if code_cost > 0:
            credit(user["id"], code_cost, "code_refund", f"Remboursement PiCode : {title}")
        raise
    bot_id = ensure_code_bot()
    message = save_message(
        room_id,
        bot_id,
        f"🐍 {title}",
        message_type="python_code",
        metadata={
            "title": title,
            "prompt": prompt[:500],
            "code": code,
            "explanation": explanation,
            "provider": provider,
            "safe": True,
            "lines": safety["lines"],
            "cost": code_cost,
            "executed": False,
        },
    )
    with get_db_cursor() as cursor:
        cursor.execute(
            """INSERT INTO code_lab_requests
               (user_id,room_id,prompt,title,provider,status)
               VALUES (?,?,?,?,?,'created')""",
            (user["id"], room_id, prompt, title, provider),
        )
    return message
