from database import get_db_cursor

PRESETS = {"pichat-dark", "amoled", "light", "discord", "neon", "ocean", "sunset", "forest", "mono"}
DENSITIES = {"comfortable", "compact"}

DEFAULTS = {
    "app_name": "PiChat",
    "app_subtitle": "Campus Messenger",
    "welcome_message": "Bienvenue sur PiChat",
    "logo_text": "P",
    "theme_preset": "pichat-dark",
    "primary_color": "#7c5cff",
    "secondary_color": "#37b5ff",
    "accent_color": "#22d3a6",
    "density": "comfortable",
    "show_bot_hint": True,
    "show_diagnostic": True,
}


def _as_dict(row):
    if not row:
        return dict(DEFAULTS)
    return {
        "app_name": row["app_name"],
        "app_subtitle": row["app_subtitle"],
        "welcome_message": row["welcome_message"],
        "logo_text": row["logo_text"],
        "theme_preset": row["theme_preset"],
        "primary_color": row["primary_color"],
        "secondary_color": row["secondary_color"],
        "accent_color": row["accent_color"],
        "density": row["density"],
        "show_bot_hint": bool(row["show_bot_hint"]),
        "show_diagnostic": bool(row["show_diagnostic"]),
    }


def get_ui_settings():
    with get_db_cursor() as cursor:
        row = cursor.execute("SELECT * FROM ui_settings WHERE id=1").fetchone()
    return _as_dict(row)


def update_ui_settings(data):
    current = get_ui_settings()
    merged = {**current, **data}
    if merged["theme_preset"] not in PRESETS:
        raise ValueError("Thème inconnu.")
    if merged["density"] not in DENSITIES:
        raise ValueError("Densité inconnue.")
    for key in ("primary_color", "secondary_color", "accent_color"):
        value = merged[key]
        if not isinstance(value, str) or len(value) != 7 or not value.startswith("#"):
            raise ValueError("Couleur invalide.")
        try:
            int(value[1:], 16)
        except ValueError:
            raise ValueError("Couleur invalide.")
    merged["app_name"] = str(merged["app_name"]).strip()[:40] or "PiChat"
    merged["app_subtitle"] = str(merged["app_subtitle"]).strip()[:80]
    merged["welcome_message"] = str(merged["welcome_message"]).strip()[:160]
    merged["logo_text"] = str(merged["logo_text"]).strip()[:3] or "P"
    with get_db_cursor() as cursor:
        cursor.execute("""
            UPDATE ui_settings SET app_name=?,app_subtitle=?,welcome_message=?,logo_text=?,
                theme_preset=?,primary_color=?,secondary_color=?,accent_color=?,density=?,
                show_bot_hint=?,show_diagnostic=?,updated_at=datetime('now') WHERE id=1
        """, (
            merged["app_name"], merged["app_subtitle"], merged["welcome_message"], merged["logo_text"],
            merged["theme_preset"], merged["primary_color"], merged["secondary_color"], merged["accent_color"],
            merged["density"], int(bool(merged["show_bot_hint"])), int(bool(merged["show_diagnostic"])),
        ))
    return get_ui_settings()


def reset_ui_settings():
    return update_ui_settings(DEFAULTS)
