"""Auth module — `/api/auth/*` routes.

- `GET  /api/auth/me`          → echo decoded ID token claims (any signed-in user)
- `POST /api/auth/set-role`    → set Firebase custom claims (super_admin only)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from firebase_admin import auth as fb_auth
from pydantic import BaseModel, EmailStr, Field

from src.core.auth import CurrentUser, Role, UserClaims
from src.core.errors import ApiError, ApiResponse
from src.core.firebase import get_firestore, init_firebase
from src.core.logging import get_logger
from src.core.rbac import require_super_admin

router = APIRouter(prefix="/api/auth", tags=["auth"])
log = get_logger("relief.auth.router")


class MePayload(ApiResponse[UserClaims]):
    pass


@router.get("/me", response_model=MePayload)
async def me(user: CurrentUser) -> MePayload:
    """Echo the decoded ID-token claims for the calling user."""
    return MePayload(data=user)


class SetRoleRequest(BaseModel):
    uid: str = Field(..., min_length=1)
    role: Role
    org_id: str = Field(..., alias="orgId", min_length=1)

    model_config = {"populate_by_name": True}


class SetRoleResponseData(BaseModel):
    ok: bool = True
    uid: str
    role: Role
    org_id: str = Field(..., alias="orgId")

    model_config = {"populate_by_name": True}


class SetRolePayload(ApiResponse[SetRoleResponseData]):
    pass


@router.post(
    "/set-role",
    response_model=SetRolePayload,
    dependencies=[Depends(require_super_admin)],
    status_code=status.HTTP_200_OK,
)
async def set_role(body: SetRoleRequest) -> SetRolePayload:
    """Set custom claims on a Firebase user. Caller must be super_admin."""
    init_firebase()
    try:
        fb_auth.set_custom_user_claims(body.uid, {"role": body.role, "orgId": body.org_id})
    except fb_auth.UserNotFoundError as exc:
        raise ApiError(
            code="USER_NOT_FOUND",
            message=f"No Firebase user with uid={body.uid}.",
            status_code=status.HTTP_404_NOT_FOUND,
        ) from exc
    log.info("auth.role_set", uid=body.uid, role=body.role, org_id=body.org_id)

    # Mirror to Firestore /users/{uid} so app code can query roles by org without listAllUsers().
    db = get_firestore()
    db.collection("users").document(body.uid).set(
        {"role": body.role, "orgId": body.org_id}, merge=True
    )

    return SetRolePayload(
        data=SetRoleResponseData(uid=body.uid, role=body.role, orgId=body.org_id)
    )


class CreateUserRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    display_name: str = Field(..., alias="displayName", min_length=1)
    role: Role
    org_id: str = Field(..., alias="orgId", min_length=1)

    model_config = {"populate_by_name": True}


class CreateUserResponseData(BaseModel):
    uid: str
    email: str
    role: Role
    org_id: str = Field(..., alias="orgId")

    model_config = {"populate_by_name": True}


class CreateUserPayload(ApiResponse[CreateUserResponseData]):
    pass


@router.post(
    "/users",
    response_model=CreateUserPayload,
    dependencies=[Depends(require_super_admin)],
    status_code=status.HTTP_201_CREATED,
)
async def create_user(body: CreateUserRequest) -> CreateUserPayload:
    """Create a Firebase user + assign role. super_admin-only convenience for seeding."""
    init_firebase()
    try:
        record = fb_auth.create_user(
            email=body.email,
            password=body.password,
            display_name=body.display_name,
            email_verified=True,
        )
    except fb_auth.EmailAlreadyExistsError as exc:
        raise ApiError(
            code="EMAIL_EXISTS",
            message=f"User with email {body.email} already exists.",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc

    fb_auth.set_custom_user_claims(record.uid, {"role": body.role, "orgId": body.org_id})

    db = get_firestore()
    db.collection("users").document(record.uid).set(
        {
            "email": body.email,
            "displayName": body.display_name,
            "role": body.role,
            "orgId": body.org_id,
        },
        merge=True,
    )
    log.info("auth.user_created", uid=record.uid, email=body.email, role=body.role)

    return CreateUserPayload(
        data=CreateUserResponseData(
            uid=record.uid, email=body.email, role=body.role, orgId=body.org_id
        )
    )
