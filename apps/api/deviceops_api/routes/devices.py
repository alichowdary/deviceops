"""Owner-scoped device management and telemetry endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..broker_provisioning import (
    BrokerProvisioningError,
    BrokerProvisioningPartialFailure,
    broker_device_provisioner,
)
from ..database import get_database_session
from ..device_credentials import (
    derive_broker_password_from_stored_hash,
    generate_device_id,
    generate_device_secret,
    hash_device_secret,
)
from ..events import create_device_event, event_created_message
from ..models import Device, Telemetry, User
from ..mqtt_auth import MqttAuthenticationError
from ..ownership import get_owned_device_or_404
from ..schemas import (
    CapabilityStateRead,
    DeviceRead,
    DeviceRegistrationCreate,
    DeviceRegistrationRead,
    DeviceUpdate,
    TelemetryRead,
)
from ..security import get_current_user
from ..realtime import realtime_hub


router = APIRouter(prefix="/api/devices", tags=["devices"])
logger = logging.getLogger(__name__)
DatabaseSession = Annotated[Session, Depends(get_database_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.post(
    "",
    response_model=DeviceRegistrationRead,
    status_code=status.HTTP_201_CREATED,
)
def register_device(
    _request: DeviceRegistrationCreate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> DeviceRegistrationRead:
    device_id = generate_device_id()
    device_secret = generate_device_secret()
    stored_secret_hash = hash_device_secret(device_secret)
    broker_password = (
        derive_broker_password_from_stored_hash(stored_secret_hash)
        if broker_device_provisioner is not None
        else None
    )
    device = Device(
        device_id=device_id,
        owner_id=current_user.id,
        device_secret_hash=stored_secret_hash,
        status="unknown",
        first_seen_at=None,
        last_seen_at=None,
    )
    session.add(device)
    broker_provisioned = False
    try:
        session.flush()
        if broker_device_provisioner is not None:
            assert broker_password is not None
            broker_device_provisioner.provision_device(
                device.device_id, broker_password
            )
            broker_provisioned = True
        event = create_device_event(
            session,
            owner_id=current_user.id,
            device_id=device.device_id,
            event_type="device_registered",
            occurred_at=datetime.now(timezone.utc),
        )
        session.commit()
    except BrokerProvisioningError as exc:
        session.rollback()
        partial_failure = isinstance(exc, BrokerProvisioningPartialFailure)
        if partial_failure:
            logger.critical(
                "Broker provisioning and cleanup failed during registration for device %s",
                device_id,
            )
        else:
            logger.error(
                "Broker provisioning failed during registration for device %s",
                device_id,
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Device broker provisioning and cleanup failed"
                if partial_failure
                else "Device broker provisioning failed"
            ),
        ) from exc
    except SQLAlchemyError as exc:
        session.rollback()
        if broker_provisioned:
            try:
                assert broker_device_provisioner is not None
                broker_device_provisioner.revoke_device(device_id)
            except BrokerProvisioningError as compensation_error:
                logger.critical(
                    "Device registration failed and broker cleanup failed for device %s",
                    device_id,
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=(
                        "Device registration failed and broker cleanup failed"
                    ),
                ) from compensation_error
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Device registration failed",
        ) from exc

    realtime_hub.publish_from_thread(
        current_user.id, event_created_message(event)
    )

    return DeviceRegistrationRead(
        device_id=device.device_id,
        device_secret=device_secret,
        status="unknown",
        created_at=device.created_at,
    )


@router.get("", response_model=list[DeviceRead])
def list_devices(session: DatabaseSession, current_user: CurrentUser) -> list[Device]:
    return list(
        session.scalars(
            select(Device)
            .where(Device.owner_id == current_user.id)
            .order_by(Device.device_id)
        )
    )


@router.get("/{device_id}", response_model=DeviceRead)
def get_device(
    device_id: str, session: DatabaseSession, current_user: CurrentUser
) -> Device:
    return get_owned_device_or_404(session, device_id, current_user.id)


@router.patch("/{device_id}", response_model=DeviceRead)
def update_device(
    device_id: str,
    request: DeviceUpdate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> Device:
    device = get_owned_device_or_404(session, device_id, current_user.id)
    device.display_name = request.display_name
    try:
        session.commit()
        session.refresh(device)
    except SQLAlchemyError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Device update failed",
        ) from exc
    return device


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_device(
    device_id: str,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> Response:
    device = get_owned_device_or_404(session, device_id, current_user.id)
    broker_password: str | None = None
    broker_identity_was_revoked = False
    if broker_device_provisioner is not None:
        try:
            broker_password = derive_broker_password_from_stored_hash(
                device.device_secret_hash or ""
            )
        except MqttAuthenticationError as exc:
            logger.error(
                "Stored device credential is invalid during deletion for device %s",
                device_id,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Device deletion failed",
            ) from exc
        try:
            broker_identity_was_revoked = (
                broker_device_provisioner.revoke_device(device_id)
            )
        except BrokerProvisioningError as exc:
            session.rollback()
            logger.error(
                "Broker revocation failed during deletion for device %s",
                device_id,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Device broker revocation failed",
            ) from exc

    try:
        session.delete(device)
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        if (
            broker_device_provisioner is not None
            and broker_identity_was_revoked
        ):
            try:
                assert broker_password is not None
                broker_device_provisioner.provision_device(
                    device_id, broker_password
                )
            except BrokerProvisioningError as compensation_error:
                logger.critical(
                    "Device deletion failed and broker restoration failed for device %s",
                    device_id,
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=(
                        "Device deletion failed and broker restoration failed"
                    ),
                ) from compensation_error
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Device deletion failed",
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{device_id}/capabilities",
    response_model=CapabilityStateRead,
)
def get_device_capabilities(
    device_id: str, session: DatabaseSession, current_user: CurrentUser
) -> CapabilityStateRead:
    device = get_owned_device_or_404(session, device_id, current_user.id)
    return CapabilityStateRead(
        capabilities=device.capabilities,
        updated_at=device.capabilities_updated_at,
    )


@router.get("/{device_id}/telemetry", response_model=list[TelemetryRead])
def get_device_telemetry(
    device_id: str,
    session: DatabaseSession,
    current_user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[Telemetry]:
    get_owned_device_or_404(session, device_id, current_user.id)

    newest_first = list(
        session.scalars(
            select(Telemetry)
            .where(Telemetry.device_id == device_id)
            .order_by(Telemetry.received_at.desc(), Telemetry.id.desc())
            .limit(limit)
        )
    )
    newest_first.reverse()
    return newest_first
