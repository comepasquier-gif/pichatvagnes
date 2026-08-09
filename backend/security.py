"""
security.py
-----------
Fonctions de sécurité utilisées par le système d'authentification :
- hash et vérification des mots de passe (bcrypt)
- génération de tokens de session aléatoires et sécurisés

Choix technique : on utilise directement la librairie "bcrypt", plutôt que
"passlib" (qui l'enrobe), pour limiter les dépendances et bien comprendre
ce qui se passe. bcrypt est un algorithme conçu spécifiquement pour le hash
de mots de passe : il est volontairement lent (résistant aux attaques par
force brute) et gère automatiquement un "sel" aléatoire par mot de passe.
"""

import bcrypt
import secrets


def hash_password(plain_password: str) -> str:
    """
    Transforme un mot de passe en clair en un hash sécurisé à stocker
    en base de données.

    IMPORTANT : on ne stocke JAMAIS un mot de passe en clair. Le hash
    bcrypt inclut un sel aléatoire intégré, donc deux utilisateurs avec
    le même mot de passe auront des hash différents.
    """
    # bcrypt travaille sur des bytes, pas des chaînes de caractères.
    password_bytes = plain_password.encode("utf-8")
    hashed = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
    # On restocke le résultat en texte (str) pour l'insérer facilement
    # dans une colonne SQLite de type TEXT.
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Vérifie qu'un mot de passe en clair correspond bien à un hash stocké
    en base. Utilisé lors de la connexion.

    bcrypt.checkpw() recalcule le hash avec le même sel que celui stocké
    dans "hashed_password", puis compare les deux résultats.
    """
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except ValueError:
        # Se produit si "hashed_password" n'est pas un hash bcrypt valide
        # (ex: données corrompues). On considère alors que la vérification
        # échoue, plutôt que de laisser planter le serveur.
        return False


def generate_session_token() -> str:
    """
    Génère un token de session aléatoire, imprévisible, utilisé comme
    identifiant de connexion (stocké dans un cookie côté navigateur et
    dans la table "sessions" côté serveur).

    secrets.token_urlsafe() utilise un générateur cryptographiquement
    sûr (contrairement au module "random", qui ne doit jamais être
    utilisé pour de la sécurité).
    """
    return secrets.token_urlsafe(32)
