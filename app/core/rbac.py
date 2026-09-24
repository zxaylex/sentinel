from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.user import User
from app.models.role import Role, Permission
from app.middleware.auth_middleware import get_current_user_id


class RequirePermissions:
    """
    FastAPI dependency that checks if the current user has ALL required permissions.

    Usage:
        @router.get("/admin", dependencies=[Depends(RequirePermissions("users:read", "users:write"))])
        async def admin_endpoint():
            ...
    """

    def __init__(self, *permissions: str):
        self.required = set(permissions)

    async def __call__(
        self,
        user_id: str = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_db),
    ):
        result = await db.execute(
            select(User)
            .where(User.id == user_id)
            .options(selectinload(User.roles).selectinload(Role.permissions))
        )
        user = result.scalar_one_or_none()

        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User not found or inactive",
            )

        # Collect all permissions from all roles
        user_permissions: set[str] = set()
        for role in user.roles:
            for perm in role.permissions:
                user_permissions.add(perm.name)

        # Check if user has all required permissions
        missing = self.required - user_permissions
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permissions: {', '.join(sorted(missing))}",
            )

        return user


# Convenience alias
def require_permissions(*permissions: str):
    return Depends(RequirePermissions(*permissions))
