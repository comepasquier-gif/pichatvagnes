"""PiBrawl Arena — registre open-source des combattants.

Chaque combattant vit dans ``personnages/<id>/`` et contient au minimum :
- fighter.py : configuration Python déclarative ;
- head.png / head.webp / head.jpg : portrait.

Sécurité importante : fighter.py n'est JAMAIS importé ni exécuté. Le chargeur
analyse l'AST puis accepte uniquement une affectation littérale ``FIGHTER = {...}``.
Cela permet d'écrire les attaques en Python tout en empêchant imports, exec,
fichiers, réseau, commandes système ou code arbitraire sur le serveur public.
"""
from __future__ import annotations

import ast
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from config import PROJECT_ROOT

CHARACTERS_DIR = PROJECT_ROOT / "personnages"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
HEAD_NAMES = ("head.png", "head.webp", "head.jpg", "head.jpeg")
ATTACK_TYPES = {"spread_shot", "single_shot", "burst_shot"}
SUPER_TYPES = {"super_spread", "dash_blast", "heal_pulse"}

_cache: Tuple[float, List[Dict[str, Any]], List[str]] = (0.0, [], [])


def _num(value: Any, low: float, high: float, name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{name} doit être un nombre")
    value = float(value)
    if value < low or value > high:
        raise ValueError(f"{name} hors limites ({low}..{high})")
    return value


def _integer(value: Any, low: int, high: int, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} doit être un entier")
    if value < low or value > high:
        raise ValueError(f"{name} hors limites ({low}..{high})")
    return value


def _text(value: Any, max_len: int, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} doit être du texte")
    value = value.strip()
    if not value or len(value) > max_len:
        raise ValueError(f"{name} invalide")
    return value


def _read_literal_config(path: Path) -> Dict[str, Any]:
    source = path.read_text(encoding="utf-8")
    if len(source) > 60_000:
        raise ValueError("fighter.py trop volumineux")
    tree = ast.parse(source, filename=str(path), mode="exec")
    fighter_node = None
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            # docstring autorisée
            continue
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "FIGHTER":
            if fighter_node is not None:
                raise ValueError("une seule variable FIGHTER est autorisée")
            fighter_node = node.value
            continue
        raise ValueError("fighter.py est déclaratif : seule l'affectation FIGHTER = {...} est autorisée")
    if fighter_node is None:
        raise ValueError("variable FIGHTER manquante")
    try:
        data = ast.literal_eval(fighter_node)
    except Exception as exc:
        raise ValueError("FIGHTER doit contenir uniquement des valeurs littérales Python") from exc
    if not isinstance(data, dict):
        raise ValueError("FIGHTER doit être un dictionnaire Python")
    return data


def _head_file(folder: Path) -> Path:
    for name in HEAD_NAMES:
        candidate = folder / name
        if candidate.is_file():
            return candidate
    raise ValueError("portrait manquant : ajoute head.png, head.webp ou head.jpg")


def _validate_attack(raw: Any, super_attack: bool = False) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("attaque invalide")
    kind = _text(raw.get("type"), 24, "type d'attaque")
    allowed = SUPER_TYPES if super_attack else ATTACK_TYPES
    if kind not in allowed:
        raise ValueError("type d'attaque non supporté : " + kind)
    result = {
        "type": kind,
        "name": _text(raw.get("name", "Attaque"), 36, "nom d'attaque"),
        "damage": _integer(raw.get("damage", 250), 10, 5000, "damage"),
        "range": _num(raw.get("range", 480), 80, 1400, "range"),
        "projectile_speed": _num(raw.get("projectile_speed", 900), 100, 2400, "projectile_speed"),
        "pellets": _integer(raw.get("pellets", 1), 1, 16, "pellets"),
        "spread_deg": _num(raw.get("spread_deg", 0), 0, 100, "spread_deg"),
        "cooldown_ms": _integer(raw.get("cooldown_ms", 360), 80, 5000, "cooldown_ms"),
        "projectile_radius": _num(raw.get("projectile_radius", 7), 2, 28, "projectile_radius"),
    }
    if super_attack:
        result["knockback"] = _num(raw.get("knockback", 0), 0, 500, "knockback")
        result["charge_hits"] = _integer(raw.get("charge_hits", 8), 1, 40, "charge_hits")
    return result


def _validate_fighter(raw: Dict[str, Any], folder: Path) -> Dict[str, Any]:
    fighter_id = _text(raw.get("id", folder.name), 32, "id").lower()
    if not ID_RE.match(fighter_id):
        raise ValueError("id : lettres minuscules, chiffres, - et _ uniquement")
    if fighter_id != folder.name.lower():
        raise ValueError("l'id FIGHTER doit correspondre au nom du dossier")
    stats = raw.get("stats", {})
    if not isinstance(stats, dict):
        raise ValueError("stats doit être un dictionnaire")
    color = raw.get("color", "#48d7ff")
    if not isinstance(color, str) or not re.match(r"^#[0-9a-fA-F]{6}$", color):
        color = "#48d7ff"
    head = _head_file(folder)
    return {
        "id": fighter_id,
        "name": _text(raw.get("name", fighter_id), 32, "name"),
        "title": _text(raw.get("title", "Combattant"), 48, "title"),
        "description": _text(raw.get("description", "Combattant PiBrawl"), 240, "description"),
        "rarity": _text(raw.get("rarity", "Starter"), 24, "rarity"),
        "color": color,
        "head_url": f"/api/pibrawl/characters/{fighter_id}/head",
        "head_filename": head.name,
        "stats": {
            "max_hp": _integer(stats.get("max_hp", 4000), 500, 20000, "max_hp"),
            "speed": _num(stats.get("speed", 250), 80, 500, "speed"),
            "radius": _num(stats.get("radius", 30), 16, 54, "radius"),
            "ammo": _integer(stats.get("ammo", 3), 1, 8, "ammo"),
            "reload_ms": _integer(stats.get("reload_ms", 1400), 200, 7000, "reload_ms"),
        },
        "attack": _validate_attack(raw.get("attack", {}), False),
        "super": _validate_attack(raw.get("super", {}), True),
    }


def load_roster(force: bool = False) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Retourne (combattants, erreurs). Cache court, recharge automatique."""
    global _cache
    now = time.monotonic()
    if not force and now - _cache[0] < 2.0:
        return _cache[1], _cache[2]
    CHARACTERS_DIR.mkdir(parents=True, exist_ok=True)
    fighters: List[Dict[str, Any]] = []
    errors: List[str] = []
    for folder in sorted(CHARACTERS_DIR.iterdir(), key=lambda p: p.name.lower()):
        if not folder.is_dir() or folder.name.startswith("_") or not ID_RE.match(folder.name.lower()):
            continue
        config_path = folder / "fighter.py"
        if not config_path.is_file():
            errors.append(f"{folder.name}: fighter.py manquant")
            continue
        try:
            fighters.append(_validate_fighter(_read_literal_config(config_path), folder))
        except Exception as exc:
            errors.append(f"{folder.name}: {exc}")
    _cache = (now, fighters, errors)
    return fighters, errors


def get_fighter(fighter_id: str) -> Dict[str, Any]:
    fighter_id = (fighter_id or "").lower()
    fighters, _ = load_roster()
    for fighter in fighters:
        if fighter["id"] == fighter_id:
            return fighter
    raise KeyError(fighter_id)


def get_head_path(fighter_id: str) -> Path:
    fighter = get_fighter(fighter_id)
    folder = CHARACTERS_DIR / fighter["id"]
    head = (folder / fighter["head_filename"]).resolve()
    root = CHARACTERS_DIR.resolve()
    if root not in head.parents or not head.is_file():
        raise KeyError(fighter_id)
    return head
