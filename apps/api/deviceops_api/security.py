"""Password hashing, access-token handling, and authentication dependencies."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from sqlalchemy.orm import Session

from .config import settings
from .database import get_database_session
from .models import User


JWT_ALGORITHM = "HS256"

_password_hasher = PasswordHasher()
_dummy_password_hash = _password_hasher.hash("deviceops-dummy-password")
_bearer_scheme = HTTPBearer(auto_error=False)


class AccessTokenError(Exception):
    """Raised when an access token cannot identify an authenticated user."""


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    candidate_hash = password_hash or _dummy_password_hash
    try:
        verified = _password_hasher.verify(candidate_hash, password)
    except (InvalidHashError, VerificationError):
        return False
    return verified and password_hash is not None


def create_access_token(user_id: int) -> str:
    issued_at = datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(seconds=settings.auth_token_lifetime_seconds)
    return jwt.encode(
        {
            "sub": str(user_id),
            "iat": issued_at,
            "exp": expires_at,
        },
        settings.auth_secret,
        algorithm=JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> int:
    try:
        payload = jwt.decode(
            token,
            settings.auth_secret,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "iat", "exp"]},
        )
        subject = payload["sub"]
        if not isinstance(subject, str) or not subject.isdecimal():
            raise AccessTokenError
        user_id = int(subject)
        if user_id < 1:
            raise AccessTokenError
        return user_id
    except (InvalidTokenError, KeyError, TypeError, ValueError) as exc:
        raise AccessTokenError from exc


def _authentication_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)
    ],
    session: Annotated[Session, Depends(get_database_session)],
) -> User:
    if credentials is None:
        raise _authentication_error()
    try:
        user_id = decode_access_token(credentials.credentials)
    except AccessTokenError as exc:
        raise _authentication_error() from exc

    user = session.get(User, user_id)
    if user is None:
        raise _authentication_error()
    return user
