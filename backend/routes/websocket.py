from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from time import monotonic

from config import SESSION_COOKIE_NAME
from services.auth_service import get_user_from_session, is_user_active
from services.message_service import save_message
from services.room_service import user_can_access_room, get_default_room_id_for_user
from services.bot_service import build_bot_replies
from services.ai_service import maybe_build_ai_reply
from services.game_service import handle_game_command, award_message_xp
from connection_manager import manager
from services.moderation_service import restriction_status,get_advanced_settings,get_room_slow_mode
from services.automod_service import review_message, get_automod_settings
from services.spam_guard_service import inspect_message

router = APIRouter()




@router.websocket("/ws/notifications")
async def notification_websocket(websocket: WebSocket):
    """Flux silencieux PWA pour les salons accessibles à l'utilisateur.

    Aucun message n'est envoyé par le client sur ce canal : il sert uniquement
    aux compteurs de non-lus et notifications quand un autre salon reçoit un
    message. Les permissions sont filtrées côté serveur avant chaque diffusion.
    """
    session_token = websocket.cookies.get(SESSION_COOKIE_NAME)
    user = get_user_from_session(session_token) if session_token else None
    if user is None:
        await websocket.close(code=1008)
        return
    await manager.connect_notifications(websocket, user["id"])
    try:
        while True:
            # Le navigateur envoie un petit ping périodique. Cela permet aussi
            # de détecter rapidement une session supprimée ou un compte banni.
            await websocket.receive_text()
            current_user = get_user_from_session(session_token) if session_token else None
            if current_user is None or not is_user_active(user["id"]):
                await websocket.send_json({"type": "forced_logout", "reason": "Session expirée ou accès retiré."})
                await websocket.close(code=1008)
                break
            await websocket.send_json({"type": "notification_pong"})
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket)

@router.websocket("/ws")
async def chat_websocket(websocket: WebSocket, room_id: int = Query(default=None)):
    session_token = websocket.cookies.get(SESSION_COOKIE_NAME)
    user = get_user_from_session(session_token) if session_token else None
    if user is None:
        await websocket.close(code=1008)
        return

    if room_id is None or not user_can_access_room(user, room_id):
        room_id = get_default_room_id_for_user(user)
    if room_id is None or not user_can_access_room(user, room_id):
        await websocket.close(code=1008)
        return

    # Le mode lent reste propre à la connexion. L'anti-spam v1.1 est, lui,
    # partagé par utilisateur entre salons et reconnexions rapides.
    last_message_at = 0.0

    await manager.connect(websocket, room_id, user["id"])
    await manager.broadcast_to_room(room_id, {"type": "user_joined", "username": user["username"]})

    async def publish_automod(decision):
        """Affiche les décisions AutoModo et indique si la connexion doit être fermée."""
        if decision.get("bot_message"):
            await manager.broadcast_to_room(room_id, {"type": "new_message", "message": decision["bot_message"]})
        if not decision.get("incident"):
            return False
        sanction = decision.get("sanction") or "none"
        if sanction == "temporary_ban":
            await websocket.send_json({"type": "forced_logout", "reason": "AutoModo : exclusion temporaire après plusieurs infractions."})
            try:
                await websocket.close(code=1008)
            except Exception:
                pass
            return True
        if sanction == "mute":
            await websocket.send_json({"type": "system_notice", "level": "warning", "message": "AutoModo t'a placé en mode muet temporairement. La décision est visible par les administrateurs."})
        elif decision.get("blocked"):
            await websocket.send_json({"type": "system_notice", "level": "warning", "message": "AutoModo a bloqué ce message : " + str(decision.get("detail") or decision.get("rule") or "règle de sécurité")})
        else:
            await websocket.send_json({"type": "system_notice", "level": "warning", "message": "AutoModo a enregistré un avertissement : " + str(decision.get("detail") or decision.get("rule") or "règle de sécurité")})
        return False

    try:
        while True:
            data = await websocket.receive_json()

            # Le ban est revérifié à CHAQUE action, même si la page était déjà ouverte.
            if not is_user_active(user["id"]):
                try:
                    await websocket.send_json({"type": "forced_logout", "reason": "Ton compte a été banni."})
                finally:
                    await websocket.close(code=1008)
                break

            # Revérifie aussi que la classe donne toujours accès à ce serveur.
            current_user = get_user_from_session(session_token) if session_token else None
            if current_user is None or not user_can_access_room(current_user, room_id):
                try:
                    await websocket.send_json({"type": "forced_logout", "reason": "Ton accès à ce serveur a changé."})
                finally:
                    await websocket.close(code=1008)
                break

            content = data.get("content", "").strip()
            reply_to_id = data.get("reply_to_id")
            try:
                reply_to_id = int(reply_to_id) if reply_to_id else None
            except Exception:
                reply_to_id = None
            if not content:
                continue
            content = content[:2000]

            restriction = restriction_status(user["id"])
            if restriction and restriction.get("is_muted"):
                await websocket.send_json({"type":"system_notice","level":"warning","message":"Tu es en mode muet jusqu'au "+str(restriction.get("muted_until"))+". "+str(restriction.get("mute_reason") or "")})
                continue

            settings = get_advanced_settings()
            now = monotonic()

            room_settings = get_room_slow_mode(room_id) or {}
            slow = int(room_settings.get("slow_mode_seconds") or 0)
            if slow and not current_user.get("is_admin") and now - last_message_at < slow:
                wait = max(1, int(slow - (now - last_message_at)))
                await websocket.send_json({"type":"system_notice","level":"warning","message":f"Mode lent : attends encore {wait} seconde(s)."})
                continue

            automod_cfg = get_automod_settings()
            # L'anti-spam technique s'applique à tous les humains, y compris
            # aux admins/modos qui veulent le tester. Le réglage exempt_staff
            # empêche seulement les points/sanctions AutoModo contre le staff.
            spam = None if current_user.get("is_bot") else inspect_message(user["id"], room_id, content, settings)
            if spam:
                detail = spam["detail"]
                wait = int(spam.get("wait_seconds") or 0)
                if wait:
                    detail += f" · pause imposée : {wait}s"
                decision = review_message(
                    current_user or user, room_id, content,
                    forced_rule=spam["rule"], forced_points=spam["points"], forced_detail=detail,
                )
                if not decision.get("incident"):
                    await websocket.send_json({"type":"system_notice","level":"warning","message":"Anti-spam 1.1.3 : " + detail})
                if await publish_automod(decision):
                    break
                continue

            last_message_at = now

            # AutoModo analyse le contenu avant tout enregistrement ou commande.
            automod_decision = review_message(current_user or user, room_id, content)
            if await publish_automod(automod_decision):
                break
            if automod_decision.get("blocked") or automod_decision.get("sanction") in {"mute", "temporary_ban"}:
                continue

            # Les commandes de mini-jeux deviennent des cartes interactives et
            # ne sont pas enregistrées comme du texte brut.
            game_message = handle_game_command(room_id, current_user or user, content)
            if game_message is not None:
                await manager.broadcast_to_room(room_id, {"type": "new_message", "message": game_message})
                continue

            saved_message = save_message(room_id, user["id"], content, reply_to_id=reply_to_id)
            award_message_xp(user["id"], 2)
            try:
                from services.rpg_service import progress_quest
                progress_quest(user["id"], "messages", 1)
            except Exception:
                pass
            await manager.broadcast_to_room(room_id, {"type": "new_message", "message": saved_message})

            for bot_message in build_bot_replies(room_id, user, content):
                await manager.broadcast_to_room(room_id, {"type": "new_message", "message": bot_message})

            ai_message = await maybe_build_ai_reply(room_id, current_user or user, content)
            if ai_message:
                await manager.broadcast_to_room(room_id, {"type": "new_message", "message": ai_message})

    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket, room_id)
        await manager.broadcast_to_room(room_id, {"type": "user_left", "username": user["username"]})
