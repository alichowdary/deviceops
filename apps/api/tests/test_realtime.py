"""Isolated realtime tests: no app lifespan, broker, or database connections."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import json
import threading
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import WebSocketDisconnect
import jwt
from sqlalchemy.exc import SQLAlchemyError

from deviceops_api import main, websocket_auth
from deviceops_api.config import settings
from deviceops_api.realtime import RealtimeHub
from deviceops_api.security import AccessTokenError, create_access_token, decode_access_token


class FakeWebSocket:
    def __init__(self, *frames: dict, origin: str | None = None) -> None:
        self.headers = {"origin": origin or settings.cors_origins[0]}
        self.frames: asyncio.Queue[dict] = asyncio.Queue()
        for frame in frames:
            self.frames.put_nowait(frame)
        self.sent: list[dict] = []
        self.operations: list[tuple] = []
        self.closed: list[int] = []
        self.accepted = asyncio.Event()
        self.message_sent = asyncio.Event()

    async def accept(self) -> None:
        self.operations.append(("accept",))
        self.accepted.set()

    async def receive(self) -> dict:
        return await self.frames.get()

    async def send_json(self, event: dict) -> None:
        self.operations.append(("send", event))
        self.sent.append(event)
        self.message_sent.set()

    async def close(self, code: int) -> None:
        self.closed.append(code)


def auth_frame(token: str) -> dict:
    return {
        "type": "websocket.receive",
        "text": json.dumps({"type": "authenticate", "token": token}),
    }


DISCONNECT = {"type": "websocket.disconnect", "code": 1000}


class HubTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.hub = RealtimeHub()
        await self.hub.start()
        self.addAsyncCleanup(self.hub.stop)

    async def test_each_event_type_is_only_delivered_to_its_owner(self) -> None:
        owner_one, owner_two = FakeWebSocket(), FakeWebSocket()
        await self.hub.connect(owner_one, 1)
        await self.hub.connect(owner_two, 2)
        for event_type in (
            "telemetry",
            "device_status",
            "command_update",
            "event_created",
        ):
            for owner_id in (1, 2):
                with self.subTest(event_type=event_type, owner_id=owner_id):
                    event = {"type": event_type, "device_id": f"device-{owner_id}"}
                    await self.hub._broadcast(owner_id, event)
                    target, other = (
                        (owner_one, owner_two) if owner_id == 1 else (owner_two, owner_one)
                    )
                    self.assertEqual(target.sent, [event])
                    self.assertEqual(other.sent, [])
                    self.assertNotIn("owner_id", target.sent[0])
                    target.sent.clear()
        self.assertFalse(owner_one.accepted.is_set(), "Only the endpoint accepts sockets")

    async def test_thread_publication_drops_events_without_valid_owners(self) -> None:
        socket = FakeWebSocket()
        await self.hub.connect(socket, 1)
        with self.assertLogs("deviceops_api.realtime", level="WARNING"):
            for owner_id in (None, 0, -1, True, "1"):
                await asyncio.to_thread(
                    self.hub.publish_from_thread, owner_id, {"type": "dropped"}
                )
        event = {"type": "device_status", "device_id": "device-1"}
        await asyncio.to_thread(self.hub.publish_from_thread, 1, event)
        await asyncio.wait_for(socket.message_sent.wait(), timeout=1)
        self.assertEqual(socket.sent, [event])

    async def test_failed_socket_is_removed_without_affecting_other_sockets(self) -> None:
        broken, healthy = FakeWebSocket(), FakeWebSocket()
        broken.send_json = AsyncMock(side_effect=RuntimeError("closed socket"))
        await self.hub.connect(broken, 1)
        await self.hub.connect(healthy, 1)
        event = {"type": "telemetry"}
        with self.assertLogs("deviceops_api.realtime", level="WARNING"):
            await self.hub._broadcast(1, event)
        await self.hub._broadcast(1, event)
        self.assertEqual(healthy.sent, [event, event])
        broken.send_json.assert_awaited_once()
        self.assertNotIn(broken, self.hub._connections)

    async def test_disconnect_and_shutdown_clean_up_connections(self) -> None:
        disconnected, active = FakeWebSocket(), FakeWebSocket()
        await self.hub.connect(disconnected, 1)
        await self.hub.connect(active, 2)
        self.hub.disconnect(disconnected)
        self.hub.disconnect(disconnected)
        await self.hub.stop()
        self.assertEqual(disconnected.closed, [])
        self.assertEqual(active.closed, [1001])
        self.assertEqual(self.hub._connections, {})
        self.assertIsNone(self.hub._broadcast_task)
        self.hub.publish_from_thread(2, {"type": "telemetry"})
        self.assertEqual(active.sent, [])


class AuthenticationTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_malformed_or_non_text_authentication(self) -> None:
        malformed = [
            "{",
            "[]",
            "null",
            json.dumps({"type": "authenticate"}),
            json.dumps({"token": "token"}),
            json.dumps({"type": "authenticate", "token": "token", "extra": True}),
            json.dumps({"type": "telemetry", "token": "token"}),
            json.dumps({"type": "authenticate", "token": ""}),
            json.dumps({"type": "authenticate", "token": "   "}),
            json.dumps({"type": "authenticate", "token": 123}),
            '{"type":"authenticate","token":"first","token":"second"}',
        ]
        frames = [{"type": "websocket.receive", "text": text} for text in malformed]
        frames.append({"type": "websocket.receive", "bytes": b"authenticate"})
        with patch.object(websocket_auth, "SessionLocal") as session_factory:
            for frame in frames:
                with self.subTest(frame=frame), self.assertRaises(AccessTokenError):
                    await websocket_auth.authenticate_websocket(FakeWebSocket(frame))
            session_factory.assert_not_called()

    async def test_invalid_expired_or_wrongly_signed_jwt_never_queries_database(self) -> None:
        now = datetime.now(timezone.utc)
        valid_claims = {"sub": "7", "iat": now, "exp": now + timedelta(hours=1)}
        invalid_tokens = [
            "not-a-jwt",
            jwt.encode(valid_claims, settings.auth_secret + "wrong-key", algorithm="HS256"),
            jwt.encode(
                {"sub": "7", "iat": now - timedelta(hours=2), "exp": now - timedelta(hours=1)},
                settings.auth_secret,
                algorithm="HS256",
            ),
        ]
        with patch.object(websocket_auth, "SessionLocal") as session_factory:
            for token in invalid_tokens:
                with self.subTest(token_kind=invalid_tokens.index(token)):
                    with self.assertRaises(AccessTokenError):
                        await websocket_auth.authenticate_websocket(FakeWebSocket(auth_frame(token)))
            session_factory.assert_not_called()

    async def test_reuses_decoder_and_closes_lookup_session_before_returning_id(self) -> None:
        token = create_access_token(7)
        context = MagicMock()
        session = context.__enter__.return_value
        lookup_threads = []

        def found_user(_statement):
            lookup_threads.append(threading.get_ident())
            return 7

        session.scalar.side_effect = found_user
        with (
            patch.object(websocket_auth, "SessionLocal", return_value=context) as factory,
            patch.object(websocket_auth, "decode_access_token", wraps=decode_access_token) as decode,
        ):
            identity = await websocket_auth.authenticate_websocket(FakeWebSocket(auth_frame(token)))
        self.assertEqual(identity, 7)
        self.assertIs(type(identity), int)
        decode.assert_called_once_with(token)
        factory.assert_called_once_with()
        session.scalar.assert_called_once()
        context.__exit__.assert_called_once_with(None, None, None)
        self.assertNotEqual(lookup_threads[0], threading.get_ident())

    async def test_deleted_user_is_rejected_and_lookup_session_is_closed(self) -> None:
        context = MagicMock()
        context.__enter__.return_value.scalar.return_value = None
        with patch.object(websocket_auth, "SessionLocal", return_value=context):
            with self.assertRaises(AccessTokenError):
                await websocket_auth.authenticate_websocket(
                    FakeWebSocket(auth_frame(create_access_token(7)))
                )
        context.__exit__.assert_called_once_with(None, None, None)

    async def test_disconnect_during_handshake_does_not_query_database(self) -> None:
        with patch.object(websocket_auth, "SessionLocal") as factory:
            with self.assertRaises(WebSocketDisconnect):
                await websocket_auth.authenticate_websocket(FakeWebSocket(DISCONNECT))
        factory.assert_not_called()


class EndpointTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.hub = RealtimeHub()
        hub_patch = patch.object(main, "realtime_hub", self.hub)
        hub_patch.start()
        self.addCleanup(hub_patch.stop)
        self.addAsyncCleanup(self.hub.stop)

    async def test_success_control_precedes_registration_and_disconnect_cleans_up(self) -> None:
        socket = FakeWebSocket(DISCONNECT)
        connect = self.hub.connect

        async def record_connect(websocket, user_id):
            socket.operations.append(("connect", user_id))
            await connect(websocket, user_id)

        with (
            patch.object(main, "authenticate_websocket", new=AsyncMock(return_value=7)) as authenticate,
            patch.object(self.hub, "connect", side_effect=record_connect),
        ):
            await main.websocket_events(socket)
        authenticate.assert_awaited_once_with(socket)
        self.assertEqual(
            socket.operations,
            [("accept",), ("send", {"type": "authenticated"}), ("connect", 7)],
        )
        self.assertEqual(self.hub._connections, {})

    async def test_pending_authentication_receives_no_events_and_times_out(self) -> None:
        socket = FakeWebSocket()
        self.assertEqual(main.WEBSOCKET_AUTH_TIMEOUT_SECONDS, 5)
        with patch.object(main, "WEBSOCKET_AUTH_TIMEOUT_SECONDS", 0.05):
            task = asyncio.create_task(main.websocket_events(socket))
            try:
                await asyncio.wait_for(socket.accepted.wait(), timeout=1)
                await self.hub._broadcast(7, {"type": "telemetry"})
                self.assertEqual(socket.sent, [])
                self.assertEqual(self.hub._connections, {})
                await asyncio.wait_for(task, timeout=1)
            finally:
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
        self.assertEqual(socket.closed, [1008])
        self.assertEqual(socket.sent, [])
        self.assertEqual(self.hub._connections, {})

    async def test_invalid_authentication_or_database_error_closes_safely(self) -> None:
        for error in (AccessTokenError("sensitive-value"), SQLAlchemyError("sensitive-value")):
            with self.subTest(error_type=type(error).__name__):
                socket = FakeWebSocket()
                with (
                    patch.object(main, "authenticate_websocket", new=AsyncMock(side_effect=error)),
                    self.assertLogs("deviceops_api.main", level="WARNING") as logs,
                ):
                    await main.websocket_events(socket)
                self.assertEqual(socket.closed, [1008])
                self.assertEqual(socket.sent, [])
                self.assertEqual(self.hub._connections, {})
                self.assertNotIn("sensitive-value", " ".join(logs.output))

    async def test_disconnect_before_authentication_does_not_register(self) -> None:
        socket = FakeWebSocket(DISCONNECT)
        await main.websocket_events(socket)
        self.assertEqual(socket.sent, [])
        self.assertEqual(self.hub._connections, {})

    async def test_disconnect_while_sending_success_control_does_not_register(self) -> None:
        socket = FakeWebSocket()
        socket.send_json = AsyncMock(side_effect=WebSocketDisconnect())
        with patch.object(main, "authenticate_websocket", new=AsyncMock(return_value=7)):
            await main.websocket_events(socket)
        self.assertEqual(self.hub._connections, {})

    async def test_missing_or_disallowed_origin_is_rejected_before_accept(self) -> None:
        for origin in (None, "https://untrusted.example"):
            with self.subTest(origin=origin):
                socket = FakeWebSocket()
                socket.headers = {} if origin is None else {"origin": origin}
                with patch.object(main, "authenticate_websocket", new=AsyncMock()) as authenticate:
                    await main.websocket_events(socket)
                self.assertFalse(socket.accepted.is_set())
                self.assertEqual(socket.closed, [1008])
                self.assertEqual(socket.sent, [])
                authenticate.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
