"""Role-based access control — dependency factory for route handlers."""
from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, status

from src.core.auth import CurrentUser, Role, UserClaims
from src.core.errors import ApiError


def require_role(*allowed: Role) -> Callable[[UserClaims], UserClaims]:
    """Return a FastAPI dependency that 403s unless the caller's role is in `allowed`.

    Usage:
        @router.post("/disasters", dependencies=[Depends(require_role("ngo_admin"))])
    """
    allowed_set = set(allowed)

    def _guard(user: CurrentUser) -> UserClaims:
        if user.role is None or user.role not in allowed_set:
            raise ApiError(
                code="FORBIDDEN",
                message=f"This action requires one of: {sorted(allowed_set)}.",
                status_code=status.HTTP_403_FORBIDDEN,
                details={"required": sorted(allowed_set), "actual": user.role},
            )
        return user

    return _guard


# Convenience dependencies for the common admin-or-coordinator combo.
require_admin = require_role("super_admin", "ngo_admin")
require_admin_or_coord = require_role("super_admin", "ngo_admin", "coordinator")
require_super_admin = require_role("super_admin")
