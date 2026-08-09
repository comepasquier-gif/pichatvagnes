from __future__ import annotations
from typing import Dict, List, Optional
from time import monotonic
from fastapi import WebSocket


class ConnectionManager:
    """Connexions actives regroupées par salon, avec suivi par utilisateur."""

    def __init__(self):
        self.active_connections: Dict[int, List[WebSocket]] = {}
        self.connection_users: Dict[WebSocket, int] = {}
        # Connexions silencieuses utilisées par la PWA pour les compteurs et
        # notifications de tous les salons accessibles.
        self.notification_connections: Dict[WebSocket, int] = {}
        # Présences web hors WebSocket (ex. un admin dans /admin).
        self.special_presences: Dict[int, dict] = {}

    async def connect(self, websocket: WebSocket, room_id: int, user_id: int) -> None:
        await websocket.accept()
        self.active_connections.setdefault(room_id, []).append(websocket)
        self.connection_users[websocket] = user_id

    async def connect_notifications(self, websocket: WebSocket, user_id: int) -> None:
        await websocket.accept()
        self.notification_connections[websocket] = int(user_id)
        self.connection_users[websocket] = int(user_id)

    def disconnect(self, websocket: WebSocket, room_id: Optional[int] = None) -> None:
        self.connection_users.pop(websocket, None)
        self.notification_connections.pop(websocket, None)
        room_ids = [room_id] if room_id is not None else list(self.active_connections.keys())
        for rid in room_ids:
            connections = self.active_connections.get(rid, [])
            if websocket in connections:
                connections.remove(websocket)
            if rid in self.active_connections and not self.active_connections[rid]:
                del self.active_connections[rid]

    async def disconnect_user(self, user_id: int, code: int = 1008) -> int:
        """Ferme immédiatement toutes les connexions d'un utilisateur."""
        sockets = [ws for ws, uid in list(self.connection_users.items()) if uid == user_id]
        for ws in sockets:
            try:
                await ws.send_json({"type": "forced_logout", "reason": "Compte banni ou accès retiré."})
            except Exception:
                pass
            try:
                await ws.close(code=code)
            except Exception:
                pass
            self.disconnect(ws)
        return len(sockets)

    async def send_to_user(self, user_id: int, message: dict) -> int:
        sockets = [ws for ws, uid in list(self.connection_users.items()) if uid == user_id]
        sent = 0
        for ws in sockets:
            try:
                await ws.send_json(message)
                sent += 1
            except Exception:
                self.disconnect(ws)
        return sent

    async def send_room_notification(self, room_id: int, message: dict) -> int:
        """Envoie un événement PWA uniquement aux utilisateurs autorisés."""
        try:
            from services.room_service import list_room_recipient_user_ids
            recipients = set(list_room_recipient_user_ids(room_id))
        except Exception:
            recipients = set()
        sent = 0
        payload = {"type": "room_notification", "room_id": int(room_id), "message": message.get("message")}
        for ws, uid in list(self.notification_connections.items()):
            if uid not in recipients:
                continue
            try:
                await ws.send_json(payload)
                sent += 1
            except Exception:
                self.disconnect(ws)
        return sent

    def online_user_ids(self, room_id: Optional[int] = None) -> set[int]:
        if room_id is None:
            return set(self.connection_users.values())
        return {self.connection_users.get(ws) for ws in self.active_connections.get(room_id, []) if self.connection_users.get(ws) is not None}


    def set_special_presence(self, user_id: int, status: str, kind: str = "special", ttl_seconds: int = 45) -> None:
        self.special_presences[int(user_id)] = {
            "status": str(status)[:120],
            "kind": str(kind)[:40],
            "expires_at": monotonic() + max(10, int(ttl_seconds)),
        }

    def clear_special_presence(self, user_id: int) -> None:
        self.special_presences.pop(int(user_id), None)

    def special_presence_map(self) -> dict[int, dict]:
        now = monotonic()
        expired = [uid for uid, item in self.special_presences.items() if item.get("expires_at", 0) <= now]
        for uid in expired:
            self.special_presences.pop(uid, None)
        return {uid: {"status": item["status"], "kind": item["kind"]} for uid, item in self.special_presences.items()}

    async def disconnect_all(self, reason: str = "Maintenance PiChat", code: int = 1012) -> int:
        sockets = list(self.connection_users.keys())
        for ws in sockets:
            try:
                await ws.send_json({"type": "maintenance", "reason": reason})
            except Exception:
                pass
            try:
                await ws.close(code=code)
            except Exception:
                pass
            self.disconnect(ws)
        return len(sockets)

    async def broadcast_to_room(self, room_id: int, message: dict) -> None:
        for connection in list(self.active_connections.get(room_id, [])):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection, room_id)
        if message.get("type") == "new_message" and message.get("message"):
            await self.send_room_notification(room_id, message)


manager = ConnectionManager()
