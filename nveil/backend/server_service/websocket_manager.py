# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Centralized WebSocket connection management for the server service.

Session-level architecture: each browser tab opens one WS (conn_id).
Tabs subscribe to rooms dynamically via {"action": "subscribe", "room_token": "..."}.
Multiple tabs can subscribe to the same room and all receive events.
"""

from typing import Dict, Optional, Set

from fastapi import WebSocket
from logger import DEBUG, ERROR, INFO, WARNING, logger


class WebSocketManager:
    """Manages WebSocket connections keyed by connection ID with room subscriptions."""

    def __init__(self):
        self._connections: Dict[str, WebSocket] = {}        # conn_id -> ws
        self._subscriptions: Dict[str, Set[str]] = {}       # room_token -> {conn_id, ...}
        self._conn_rooms: Dict[str, str] = {}               # conn_id -> room_token
        self._conn_owners: Dict[str, str] = {}              # conn_id -> owner_id
        self._last_events: Dict[str, dict] = {}             # room_token -> last event

    @property
    def connections(self) -> Dict[str, WebSocket]:
        return self._connections

    def connect(self, conn_id: str, ws: WebSocket):
        self._connections[conn_id] = ws
        logger().logp(INFO, f"✅ WebSocket connected [conn_id: {conn_id[:8]}...]")

    def disconnect(self, conn_id: str):
        ws = self._connections.pop(conn_id, None)
        # Clean up subscription
        old_room = self._conn_rooms.pop(conn_id, None)
        if old_room and old_room in self._subscriptions:
            self._subscriptions[old_room].discard(conn_id)
            if not self._subscriptions[old_room]:
                del self._subscriptions[old_room]
        self._conn_owners.pop(conn_id, None)
        if ws:
            logger().logp(INFO, f"WebSocket disconnected [conn_id: {conn_id[:8]}...]")

    def subscribe(self, conn_id: str, room_token: str):
        """Subscribe a connection to a room. Unsubscribes from previous room if any."""
        # Unsubscribe from previous room
        old_room = self._conn_rooms.get(conn_id)
        if old_room:
            if old_room in self._subscriptions:
                self._subscriptions[old_room].discard(conn_id)
                if not self._subscriptions[old_room]:
                    del self._subscriptions[old_room]
        # Subscribe to new room
        if room_token not in self._subscriptions:
            self._subscriptions[room_token] = set()
        self._subscriptions[room_token].add(conn_id)
        self._conn_rooms[conn_id] = room_token
        logger().logp(INFO, f"📡 Connection {conn_id[:8]}... subscribed to room {room_token[:8]}...")

    def get(self, room_token: str) -> WebSocket | None:
        """Get the first WebSocket subscribed to a room (backward compat)."""
        conn_ids = self._subscriptions.get(room_token, set())
        for cid in conn_ids:
            ws = self._connections.get(cid)
            if ws:
                return ws
        return None

    def re_register(self, old_token: str, new_token: str):
        """Move all subscriptions from one room token to another."""
        conn_ids = self._subscriptions.pop(old_token, set())
        if conn_ids:
            if new_token not in self._subscriptions:
                self._subscriptions[new_token] = set()
            for cid in conn_ids:
                self._subscriptions[new_token].add(cid)
                self._conn_rooms[cid] = new_token
            logger().logp(INFO, f"🔄 Subscriptions re-registered: {old_token[:8]}... → {new_token[:8]}... ({len(conn_ids)} connections)")

    def get_last_event(self, room_token: str):
        return self._last_events.get(room_token)

    async def send(self, room_token: str, event_data: dict):
        """Send a JSON message to all WebSockets subscribed to *room_token*."""
        self._last_events[room_token] = event_data
        conn_ids = self._subscriptions.get(room_token, set())
        for cid in list(conn_ids):
            ws = self._connections.get(cid)
            if ws:
                try:
                    await ws.send_json(event_data)
                except Exception as e:
                    logger().logp(ERROR, f"Failed to send to {cid[:8]}...: {e}")
                    self.disconnect(cid)

    def set_owner(self, conn_id: str, owner_id: str):
        """Associate a connection with a user (owner_id)."""
        self._conn_owners[conn_id] = owner_id

    async def send_to_user(self, owner_id: str, event_data: dict):
        """Send a JSON message to all WebSockets belonging to a specific user."""
        for cid, oid in list(self._conn_owners.items()):
            if oid == owner_id:
                ws = self._connections.get(cid)
                if ws:
                    try:
                        await ws.send_json(event_data)
                    except Exception as e:
                        logger().logp(ERROR, f"Failed to send to user {owner_id[:8]}: {e}")
                        self.disconnect(cid)

    async def broadcast(self, event_data: dict):
        """Broadcast a JSON message to ALL connected WebSockets."""
        for cid, ws in list(self._connections.items()):
            try:
                await ws.send_json(event_data)
            except Exception as e:
                logger().logp(ERROR, f"Failed to broadcast to {cid[:8]}...: {e}")
                self.disconnect(cid)
    
    async def broadcast_to_user(self, user_id: str, message: dict):
        """Broadcast a message to all WebSocket connections for a specific user."""
        connections_to_notify = []
        for conn_id, data in self._connections.items():
            if data.get("user_id") == user_id:
                connections_to_notify.append(data["websocket"])
        
        for ws in connections_to_notify:
            try:
                await ws.send_json(message)
            except Exception as e:
                logger().logp(WARNING, f"Failed to send force_logout to user {user_id}: {e}")


# Singleton instance — imported by server.py and route modules
ws_manager = WebSocketManager()
