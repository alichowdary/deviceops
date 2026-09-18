"""Standalone user registration and authentication endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_database_session
from ..models import User
from ..schemas import TokenRead, UserLogin, UserRead, UserRegister
from ..security import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)


router = APIRouter(prefix="/api/auth", tags=["auth"])
DatabaseSession = Annotated[Session, Depends(get_database_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
)
def register_user(request: UserRegister, session: DatabaseSession) -> User:
    existing_user = session.scalar(select(User).where(User.email == request.email))
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered",
        )

    user = User(email=request.email, password_hash=hash_password(request.password))
    session.add(user)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered",
        ) from exc
    return user


@router.post("/login", response_model=TokenRead)
def login_user(request: UserLogin, session: DatabaseSession) -> TokenRead:
    user = session.scalar(select(User).where(User.email == request.email))
    if not verify_password(request.password, user.password_hash if user else None):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    assert user is not None

    return TokenRead(
        access_token=create_access_token(user.id),
        expires_in=settings.auth_token_lifetime_seconds,
    )


@router.get("/me", response_model=UserRead)
def read_current_user(current_user: CurrentUser) -> User:
    return current_user
