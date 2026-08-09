from __future__ import annotations
from typing import Optional

import json
from fastapi import HTTPException, status

ROLE_HIERARCHY = ["player", "moderator", "admin"]

# Les permissions sont volontairement explicites : un modo peut avoir des
# pouvoirs différents d'un autre tout en restant limité à sa classe.
MODERATOR_PERMISSION_DEFINITIONS = {
    "reports_view": "Voir les signalements de sa classe",
    "reports_resolve": "Résoudre ou rejeter les signalements",
    "messages_delete": "Supprimer des messages de sa classe",
    "users_warn": "Envoyer des avertissements",
    "users_mute": "Mettre en sourdine / retirer le mute",
    "users_kick": "Expulser une session sans bannir",
    "users_tempban": "Appliquer un ban temporaire",
    "users_ban": "Bannir définitivement",
    "users_unban": "Débannir",
    "notes_manage": "Lire et écrire les notes privées",
    "history_view": "Voir l'historique des sanctions",
    "slowmode_manage": "Régler le mode lent de sa classe",
    "automod_review": "Réviser les incidents AutoModo de sa classe",
}

# Packs prêts à l'emploi. Ils ne changent jamais la règle principale :
# un modérateur ne peut agir que dans sa classe et sur des joueurs.
MODERATOR_PACK_DEFINITIONS = {
    "small": {
        "label": "Petit modo",
        "short_label": "PETIT MODO",
        "description": "Surveille, traite les signalements simples, supprime un message et avertit.",
        "color": "#57f287",
        "permissions": [
            "reports_view",
            "messages_delete",
            "users_warn",
        ],
    },
    "standard": {
        "label": "Modo normal",
        "short_label": "MODO NORMAL",
        "description": "Pack quotidien complet : signalements, suppression, mute, expulsion, ban temporaire, notes et mode lent.",
        "color": "#5865f2",
        "permissions": [
            "reports_view",
            "reports_resolve",
            "messages_delete",
            "users_warn",
            "users_mute",
            "users_kick",
            "users_tempban",
            "notes_manage",
            "history_view",
            "slowmode_manage",
        ],
    },
    "super": {
        "label": "Super modo",
        "short_label": "SUPER MODO",
        "description": "Tous les pouvoirs de modération de sa classe, y compris bans définitifs et révision AutoModo.",
        "color": "#eb459e",
        "permissions": list(MODERATOR_PERMISSION_DEFINITIONS.keys()),
    },
}

MODERATOR_PACK_ALIASES = {
    "small": "small", "petit": "small", "petit-modo": "small", "petit_modo": "small",
    "standard": "standard", "normal": "standard", "modo": "standard", "modo-normal": "standard",
    "super": "super", "super-modo": "super", "super_modo": "super", "all": "super", "tout": "super",
}

DEFAULT_MODERATOR_PACK = "standard"
DEFAULT_MODERATOR_PERMISSIONS = set(MODERATOR_PACK_DEFINITIONS[DEFAULT_MODERATOR_PACK]["permissions"])


def normalize_moderator_pack(value: Optional[str], *, allow_custom: bool = False) -> Optional[str]:
    key = str(value or "").strip().lower().replace(" ", "-")
    if not key:
        return None
    if allow_custom and key in {"custom", "personnalise", "personnalisé"}:
        return "custom"
    return MODERATOR_PACK_ALIASES.get(key)


def moderator_permissions_for_pack(value: str) -> list[str]:
    pack = normalize_moderator_pack(value)
    if not pack:
        raise ValueError("Pack de modération inconnu.")
    return sorted(MODERATOR_PACK_DEFINITIONS[pack]["permissions"])


def identify_moderator_pack(value) -> str:
    selected = set(normalize_moderator_permissions(value))
    for key, pack in MODERATOR_PACK_DEFINITIONS.items():
        if selected == set(pack["permissions"]):
            return key
    return "custom"


def moderator_pack_catalog() -> list[dict]:
    result = []
    for key, pack in MODERATOR_PACK_DEFINITIONS.items():
        permissions = sorted(pack["permissions"])
        result.append({
            "key": key,
            "label": pack["label"],
            "short_label": pack["short_label"],
            "description": pack["description"],
            "color": pack["color"],
            "permissions": permissions,
            "permission_count": len(permissions),
        })
    return result


def get_user_role(user: dict) -> str:
    if user.get("is_admin"):
        return "admin"
    if user.get("is_moderator"):
        return "moderator"
    return "player"


def get_role_label(user: dict) -> str:
    custom = (user.get("grade_title") or "").strip()
    if custom:
        return custom[:24].upper()
    role = get_user_role(user)
    if role == "admin":
        return "ADMIN"
    if role == "moderator":
        return "MODO " + (user.get("moderator_class_code") or user.get("class_code") or "")
    return "JOUEUR"


def has_permission(user: dict, required_role: str) -> bool:
    user_role = get_user_role(user)
    if user_role not in ROLE_HIERARCHY or required_role not in ROLE_HIERARCHY:
        return False
    return ROLE_HIERARCHY.index(user_role) >= ROLE_HIERARCHY.index(required_role)


def require_role(user: dict, required_role: str) -> None:
    if not has_permission(user, required_role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Droits insuffisants pour cette action.")


def normalize_moderator_permissions(value) -> list[str]:
    """Retourne une liste sûre et stable de permissions connues."""
    if value is None or value == "":
        return sorted(DEFAULT_MODERATOR_PERMISSIONS)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            value = parsed if isinstance(parsed, list) else value.split(",")
        except Exception:
            value = value.split(",")
    if not isinstance(value, (list, tuple, set)):
        return sorted(DEFAULT_MODERATOR_PERMISSIONS)
    cleaned = []
    for item in value:
        key = str(item or "").strip().lower()
        if key in MODERATOR_PERMISSION_DEFINITIONS and key not in cleaned:
            cleaned.append(key)
    return sorted(cleaned)


def serialize_moderator_permissions(value) -> str:
    return json.dumps(normalize_moderator_permissions(value), ensure_ascii=False, separators=(",", ":"))


def get_moderator_permissions(user: dict) -> list[str]:
    if user.get("is_admin"):
        return sorted(MODERATOR_PERMISSION_DEFINITIONS)
    if not user.get("is_moderator"):
        return []
    return normalize_moderator_permissions(user.get("moderator_permissions"))


def moderator_has_permission(user: dict, permission: str) -> bool:
    if user.get("is_admin"):
        return True
    if not user.get("is_moderator"):
        return False
    return permission in get_moderator_permissions(user)


def require_moderator_permission(user: dict, permission: str) -> None:
    if moderator_has_permission(user, permission):
        return
    label = MODERATOR_PERMISSION_DEFINITIONS.get(permission, permission)
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Permission de modération manquante : {label}.",
    )


def moderator_can_manage(user: dict, target: dict) -> bool:
    if user.get("is_admin"):
        return True
    if not user.get("is_moderator"):
        return False
    if target.get("is_admin") or target.get("is_bot") or target.get("is_moderator"):
        return False
    return bool(user.get("moderator_class_code")) and target.get("class_code") == user.get("moderator_class_code")
