from __future__ import annotations
from typing import Optional

"""Anti-spam v1.1.

Le garde fonctionne en mémoire, à l'échelle du processus PiChat. Il suit un
utilisateur entre plusieurs salons et même après une reconnexion rapide. Les
sanctions officielles restent confiées à AutoModo, afin qu'elles soient
journalisées et révisables par un humain.
"""

from collections import deque
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from threading import RLock
from time import monotonic
import re
import unicodedata


@dataclass
class SpamState:
    attempts: deque = field(default_factory=lambda: deque(maxlen=80))
    blocked_until: float = 0.0
    strikes: int = 0
    last_strike_at: float = 0.0


_STATES: dict[int, SpamState] = {}
_LOCK = RLock()


def _normalize(content: str) -> str:
    text = unicodedata.normalize("NFKD", content or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    text = re.sub(r"https?://\S+|www\.\S+", "<lien>", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _fingerprint(content: str) -> str:
    return re.sub(r"[^a-z0-9à-öø-ÿ]+", "", _normalize(content))


def _emoji_count(content: str) -> int:
    # Les catégories Unicode So/Sk couvrent l'essentiel des emojis utilisés
    # dans un chat, sans dépendance externe.
    return sum(1 for ch in content if unicodedata.category(ch) in {"So", "Sk"})


def _repeated_word_count(content: str) -> int:
    words = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9_'-]+", content.lower())
    if not words:
        return 0
    longest = 1
    run = 1
    for previous, current in zip(words, words[1:]):
        if current == previous:
            run += 1
            longest = max(longest, run)
        else:
            run = 1
    return longest


def _violation(rule: str, points: int, detail: str, wait: int = 0) -> dict:
    return {"rule": rule, "points": points, "detail": detail, "wait_seconds": max(0, int(wait))}


def inspect_message(user_id: int, room_id: int, content: str, settings: dict) -> Optional[dict]:
    """Analyse une tentative et retourne une infraction bloquante éventuelle."""
    now = monotonic()
    normalized = _normalize(content)
    fingerprint = _fingerprint(content)

    with _LOCK:
        state = _STATES.setdefault(int(user_id), SpamState())
        # Oublie l'historique ancien, tout en gardant assez de recul pour le
        # débit soutenu et les copier-coller entre salons.
        while state.attempts and now - state.attempts[0][0] > 600:
            state.attempts.popleft()
        if state.strikes and now - state.last_strike_at > 300:
            state.strikes = max(0, state.strikes - 1)

        if now < state.blocked_until:
            wait = max(1, round(state.blocked_until - now))
            state.attempts.append((now, room_id, normalized, fingerprint))
            return _violation("cooldown", 1, f"Cooldown anti-spam encore actif ({wait}s)", wait)

        prior = list(state.attempts)
        result = None

        # Rafale instantanée : utile sur mobile où plusieurs appuis peuvent
        # envoyer très vite. Cette règle est volontairement séparée de la
        # rafale classique pour réagir dès le 3e message.
        rapid_window = float(settings.get("rapid_window_seconds") or 1.8)
        rapid_count = int(settings.get("rapid_count") or 3)
        rapid = [x for x in prior if now - x[0] <= rapid_window]
        if len(rapid) >= max(1, rapid_count - 1):
            result = _violation("rapid_fire", 2, f"{len(rapid)+1} messages en {rapid_window:g}s")

        burst_window = float(settings.get("burst_window_seconds") or 4)
        burst_count = int(settings.get("burst_count") or 5)
        burst = [x for x in prior if now - x[0] <= burst_window]
        if result is None and settings.get("burst_enabled", True) and len(burst) >= max(1, burst_count - 1):
            result = _violation("burst", 2, f"Rafale de {len(burst)+1} messages en {burst_window:g}s")

        if result is None:
            rate_window = float(settings.get("rate_limit_window_seconds") or 20)
            rate_count = int(settings.get("rate_limit_count") or 12)
            sustained = [x for x in prior if now - x[0] <= rate_window]
            if len(sustained) >= max(1, rate_count - 1):
                result = _violation("rate_limit", 2, f"Débit soutenu : {len(sustained)+1} messages en {rate_window:g}s")

        if result is None and settings.get("duplicate_enabled", True) and normalized:
            duplicate_window = float(settings.get("duplicate_window_seconds") or 45)
            if any(now - x[0] <= duplicate_window and x[2] == normalized for x in prior):
                result = _violation("duplicate", 2, "Message identique déjà envoyé récemment")

        if result is None and settings.get("similarity_enabled", True) and len(fingerprint) >= int(settings.get("similarity_min_length") or 12):
            similarity_window = float(settings.get("similarity_window_seconds") or 90)
            ratio_limit = float(settings.get("similarity_ratio") or 0.88)
            for event in reversed(prior):
                if now - event[0] > similarity_window:
                    break
                other = event[3]
                if len(other) < int(settings.get("similarity_min_length") or 12):
                    continue
                ratio = SequenceMatcher(None, fingerprint, other).ratio()
                if ratio >= ratio_limit:
                    result = _violation("near_duplicate", 2, f"Message très proche d'un envoi récent ({round(ratio*100)} %)")
                    break

        repeat_chars = int(settings.get("repeated_char_limit") or 14)
        if result is None and repeat_chars > 0 and re.search(r"(.)\1{" + str(max(2, repeat_chars - 1)) + r",}", content, flags=re.I):
            result = _violation("character_flood", 1, f"Caractère répété au moins {repeat_chars} fois")

        punctuation_limit = int(settings.get("punctuation_limit") or 12)
        if result is None and punctuation_limit > 0 and re.search(r"[!?.,;:_-]{" + str(max(3, punctuation_limit)) + r",}", content):
            result = _violation("punctuation_flood", 1, f"Ponctuation répétée au moins {punctuation_limit} fois")

        emoji_limit = int(settings.get("emoji_limit") or 16)
        emojis = _emoji_count(content)
        if result is None and emoji_limit > 0 and emojis > emoji_limit:
            result = _violation("emoji_flood", 1, f"{emojis} emojis dans un seul message (maximum {emoji_limit})")

        word_repeat_limit = int(settings.get("word_repeat_limit") or 7)
        repeated_words = _repeated_word_count(content)
        if result is None and word_repeat_limit > 0 and repeated_words >= word_repeat_limit:
            result = _violation("word_flood", 1, f"Même mot répété {repeated_words} fois de suite")

        if result is None and settings.get("uppercase_enabled", True):
            letters = [ch for ch in content if ch.isalpha()]
            min_letters = int(settings.get("uppercase_min_length") or 14)
            if len(letters) >= min_letters:
                ratio = sum(1 for ch in letters if ch.isupper()) / max(1, len(letters))
                if ratio >= float(settings.get("uppercase_ratio") or 0.82):
                    result = _violation("uppercase", 1, f"Message à {round(ratio*100)} % en majuscules")

        state.attempts.append((now, room_id, normalized, fingerprint))
        if result is not None:
            state.strikes += 1
            state.last_strike_at = now
            base = max(1, int(settings.get("cooldown_base_seconds") or 2))
            maximum = max(base, int(settings.get("cooldown_max_seconds") or 30))
            wait = min(maximum, base * (2 ** max(0, state.strikes - 1)))
            state.blocked_until = max(state.blocked_until, now + wait)
            result["wait_seconds"] = wait
            return result

        # Une séquence saine fait redescendre progressivement le niveau.
        if state.strikes and (not prior or now - prior[-1][0] > 20):
            state.strikes = max(0, state.strikes - 1)
        return None


def clear_spam_state(user_id: Optional[int] = None) -> None:
    with _LOCK:
        if user_id is None:
            _STATES.clear()
        else:
            _STATES.pop(int(user_id), None)
