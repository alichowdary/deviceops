"""One-time WebSocket authentication using the existing REST access token."""

from __future__ import annotations

import json

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from .database import SessionLocal
from .models import User
from .security import AccessTokenError, decode_access_token


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    message: dict[str, object] = {}
    for key, value in pairs:
        if key in message:
            raise ValueError("duplicate JSON object key")
        message[key] = value
    return message


def _decode_authentication_message(text: str) -> int:
    try:
        message = json.loads(text, object_pairs_hook=_unique_object)
    except (ValueError, RecursionError) as exc:
        raise AccessTokenError from exc
    if (
        not isinstance(message, dict)
        or set(message) != {"type", "token"}
        or message["type"] != "authenticate"
        or not isinstance(message["token"], str)
        or not message["token"].strip()
    ):
        raise AccessTokenError
    token = message["token"]
    user_id = decode_access_token(token)
    del message, token
    return user_id


def _user_exists(user_id: int) -> bool:
    # The session belongs to this lookup, never to the WebSocket lifetime.
    with SessionLocal() as session:
        return session.scalar(select(User.id).where(User.id == user_id)) is not None


async def authenticate_websocket(websocket: WebSocket) -> int:
    frame = await websocket.receive()
    if frame.get("type") == "websocket.disconnect":
        raise WebSocketDisconnect(frame.get("code", 1000))
    text = frame.get("text")
    if not isinstance(text, str):
        raise AccessTokenError
    user_id = _decode_authentication_message(text)
    # Keep only the identity while doing the lookup and for the live connection.
    del frame, text
    if not await run_in_threadpool(_user_exists, user_id):
        raise AccessTokenError
    return user_id
