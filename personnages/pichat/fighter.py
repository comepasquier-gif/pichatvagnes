"""PiChat — premier combattant officiel de PiBrawl Arena.

Gameplay : combattant de proximité à tir en éventail. Le concept de fusil à
plombs est un archétype classique de jeu d'arène ; les valeurs, le visuel,
le nom et les effets ci-dessous sont originaux à PiChat.
"""

FIGHTER = {
    "id": "pichat",
    "name": "PiChat",
    "title": "Gardien cyan",
    "description": "La mascotte PiChat entre dans l'arène. Très efficace à courte portée grâce à ses éclats cyan en éventail.",
    "rarity": "Starter",
    "color": "#35d6ff",
    "stats": {
        "max_hp": 4200,
        "speed": 265,
        "radius": 30,
        "ammo": 3,
        "reload_ms": 1250,
    },
    "attack": {
        "type": "spread_shot",
        "name": "Moustaches Plasma",
        "damage": 290,
        "range": 455,
        "projectile_speed": 1050,
        "pellets": 5,
        "spread_deg": 32,
        "cooldown_ms": 360,
        "projectile_radius": 7,
    },
    "super": {
        "type": "super_spread",
        "name": "Miaou Tonnerre",
        "damage": 245,
        "range": 610,
        "projectile_speed": 1180,
        "pellets": 9,
        "spread_deg": 52,
        "cooldown_ms": 700,
        "projectile_radius": 9,
        "knockback": 210,
        "charge_hits": 8,
    },
}
