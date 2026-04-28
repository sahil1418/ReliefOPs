"""Firebase ID-token verification + FastAPI dependency."""
from __future__ import annotations

from typing import Annotated, Literal

from fastapi import Depends, Header, status
from firebase_admin import auth as fb_auth
from pydantic import BaseModel, Field

from src.core.errors import ApiError
from src.core.firebase import init_firebase
from src.core.logging import get_logger

log = get_logger("relief.auth")

Role = Literal[
    "super_admin",
    "ngo_admin",
    "coordinator",
    "volunteer",
    "beneficiary",
    "viewer",
]


class UserClaims(BaseModel):
    """Subset of the decoded Firebase ID token we expose to route handlers."""

    uid: str = Field(..., description="Firebase user id")
    email: str | None = None
    phone: str | None = None
    role: Role | None = None
    org_id: str | None = Field(default=None, alias="orgId")
    email_verified: bool = False

    model_config = {"populate_by_name": True}


def _extract_bearer(authorization: str | None) -> str:
    if not authorization:
        raise ApiError(
            code="AUTH_MISSING",
            message="Authorization header missing.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise ApiError(
            code="AUTH_MALFORMED",
            message="Authorization header must be 'Bearer <token>'.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    return parts[1].strip()


def verify_id_token(token: str) -> UserClaims:
    """Verify a Firebase ID token and return its claims.

    Always call `init_firebase()` first so the Admin SDK is configured (emulator-aware).
    """
    init_firebase()
    try:
        decoded = fb_auth.verify_id_token(token, check_revoked=False)
    except fb_auth.ExpiredIdTokenError as exc:
        raise ApiError(
            code="AUTH_EXPIRED",
            message="ID token expired.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        ) from exc
    except (fb_auth.InvalidIdTokenError, fb_auth.RevokedIdTokenError, ValueError) as exc:
        raise ApiError(
            code="AUTH_INVALID",
            message="ID token invalid.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        ) from exc

    return UserClaims(
        uid=decoded["uid"],
        email=decoded.get("email"),
        phone=decoded.get("phone_number"),
        role=decoded.get("role"),
        org_id=decoded.get("orgId"),
        email_verified=bool(decoded.get("email_verified", False)),
    )


async def get_current_user(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> UserClaims:
    """FastAPI dependency: 401 unless the request carries a valid Firebase ID token."""
    token = _extract_bearer(authorization)
    return verify_id_token(token)


CurrentUser = Annotated[UserClaims, Depends(get_current_user)]
