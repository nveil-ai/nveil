# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for WebSocketManager — connection, subscription, and event delivery."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from websocket_manager import WebSocketManager


def make_ws():
    """Create a mock WebSocket with send_json."""
    ws = AsyncMock()
    ws.send_json = AsyncMock()
    return ws


class TestConnect:
    def test_registers_connection(self):
        mgr = WebSocketManager()
        ws = make_ws()
        mgr.connect("c1", ws)
        assert "c1" in mgr.connections
        assert mgr.connections["c1"] is ws


class TestDisconnect:
    def test_removes_connection(self):
        mgr = WebSocketManager()
        mgr.connect("c1", make_ws())
        mgr.disconnect("c1")
        assert "c1" not in mgr.connections

    def test_cleans_subscription(self):
        mgr = WebSocketManager()
        mgr.connect("c1", make_ws())
        mgr.subscribe("c1", "room-a")
        mgr.disconnect("c1")
        assert "room-a" not in mgr._subscriptions

    def test_disconnect_nonexistent_no_error(self):
        mgr = WebSocketManager()
        mgr.disconnect("nonexistent")  # should not raise


class TestSubscribe:
    def test_adds_to_room(self):
        mgr = WebSocketManager()
        mgr.connect("c1", make_ws())
        mgr.subscribe("c1", "room-a")
        assert "c1" in mgr._subscriptions["room-a"]
        assert mgr._conn_rooms["c1"] == "room-a"

    def test_replaces_previous_room(self):
        mgr = WebSocketManager()
        mgr.connect("c1", make_ws())
        mgr.subscribe("c1", "room-a")
        mgr.subscribe("c1", "room-b")
        assert "c1" not in mgr._subscriptions.get("room-a", set())
        assert "c1" in mgr._subscriptions["room-b"]
        assert mgr._conn_rooms["c1"] == "room-b"


class TestGet:
    def test_returns_ws_for_subscribed_room(self):
        mgr = WebSocketManager()
        ws = make_ws()
        mgr.connect("c1", ws)
        mgr.subscribe("c1", "room-a")
        assert mgr.get("room-a") is ws

    def test_returns_none_for_empty_room(self):
        mgr = WebSocketManager()
        assert mgr.get("room-x") is None


class TestReRegister:
    def test_moves_subscriptions(self):
        mgr = WebSocketManager()
        mgr.connect("c1", make_ws())
        mgr.connect("c2", make_ws())
        mgr.subscribe("c1", "old-room")
        mgr.subscribe("c2", "old-room")
        mgr.re_register("old-room", "new-room")
        assert "old-room" not in mgr._subscriptions
        assert mgr._subscriptions["new-room"] == {"c1", "c2"}
        assert mgr._conn_rooms["c1"] == "new-room"
        assert mgr._conn_rooms["c2"] == "new-room"

    def test_empty_old_token_no_error(self):
        mgr = WebSocketManager()
        mgr.re_register("nonexistent", "new-room")
        assert "new-room" not in mgr._subscriptions


class TestSend:
    @pytest.mark.asyncio
    async def test_delivers_to_all_subscribers(self):
        mgr = WebSocketManager()
        ws1, ws2 = make_ws(), make_ws()
        mgr.connect("c1", ws1)
        mgr.connect("c2", ws2)
        mgr.subscribe("c1", "room-a")
        mgr.subscribe("c2", "room-a")
        await mgr.send("room-a", {"type": "test"})
        ws1.send_json.assert_called_once_with({"type": "test"})
        ws2.send_json.assert_called_once_with({"type": "test"})

    @pytest.mark.asyncio
    async def test_disconnects_on_send_error(self):
        mgr = WebSocketManager()
        ws = make_ws()
        ws.send_json.side_effect = Exception("connection closed")
        mgr.connect("c1", ws)
        mgr.subscribe("c1", "room-a")
        await mgr.send("room-a", {"type": "test"})
        assert "c1" not in mgr.connections


class TestGetLastEvent:
    @pytest.mark.asyncio
    async def test_caches_last_event(self):
        mgr = WebSocketManager()
        mgr.connect("c1", make_ws())
        mgr.subscribe("c1", "room-a")
        await mgr.send("room-a", {"type": "update", "data": 42})
        assert mgr.get_last_event("room-a") == {"type": "update", "data": 42}

    def test_returns_none_for_unknown_room(self):
        mgr = WebSocketManager()
        assert mgr.get_last_event("room-x") is None


class TestSendToUser:
    @pytest.mark.asyncio
    async def test_sends_to_owner_connections(self):
        mgr = WebSocketManager()
        ws1, ws2, ws3 = make_ws(), make_ws(), make_ws()
        mgr.connect("c1", ws1)
        mgr.connect("c2", ws2)
        mgr.connect("c3", ws3)
        mgr.set_owner("c1", "user-a")
        mgr.set_owner("c2", "user-a")
        mgr.set_owner("c3", "user-b")
        await mgr.send_to_user("user-a", {"type": "notify"})
        ws1.send_json.assert_called_once_with({"type": "notify"})
        ws2.send_json.assert_called_once_with({"type": "notify"})
        ws3.send_json.assert_not_called()


class TestBroadcast:
    @pytest.mark.asyncio
    async def test_sends_to_all(self):
        mgr = WebSocketManager()
        ws1, ws2 = make_ws(), make_ws()
        mgr.connect("c1", ws1)
        mgr.connect("c2", ws2)
        await mgr.broadcast({"type": "global"})
        ws1.send_json.assert_called_once_with({"type": "global"})
        ws2.send_json.assert_called_once_with({"type": "global"})
