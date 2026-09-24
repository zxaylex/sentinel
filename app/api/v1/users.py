from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from uuid import UUID

from app.database import get_db
from app.models.user import User
from app.models.role import Role
from app.schemas.user import UserDetail, UserUpdate
from app.schemas.auth import UserResponse
from app.schemas.role import AssignRolesRequest
from app.core.rbac import require_permissions
from app.core.exceptions import NotFoundException
from app.middleware.auth_middleware import get_current_user_id

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserDetail)
async def get_current_user(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get the current authenticated user's profile."""
    result = await db.execute(
        select(User).where(User.id == user_id).options(selectinload(User.roles))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundException("User not found")

    return UserDetail(
        id=user.id,
        email=user.email,
        is_active=user.is_active,
        oauth_provider=user.oauth_provider,
        created_at=user.created_at,
        updated_at=user.updated_at,
        roles=[r.name for r in user.roles],
    )


@router.get("/", response_model=list[UserDetail])
async def list_users(
    _=require_permissions("users:read"),
    db: AsyncSession = Depends(get_db),
):
    """List all users. Requires users:read permission."""
    result = await db.execute(select(User).options(selectinload(User.roles)))
    users = result.scalars().all()
    return [
        UserDetail(
            id=u.id,
            email=u.email,
            is_active=u.is_active,
            oauth_provider=u.oauth_provider,
            created_at=u.created_at,
            updated_at=u.updated_at,
            roles=[r.name for r in u.roles],
        )
        for u in users
    ]


@router.get("/{user_id}", response_model=UserDetail)
async def get_user(
    user_id: UUID,
    _=require_permissions("users:read"),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific user by ID. Requires users:read permission."""
    result = await db.execute(
        select(User).where(User.id == user_id).options(selectinload(User.roles))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundException("User not found")

    return UserDetail(
        id=user.id,
        email=user.email,
        is_active=user.is_active,
        oauth_provider=user.oauth_provider,
        created_at=user.created_at,
        updated_at=user.updated_at,
        roles=[r.name for r in user.roles],
    )


@router.patch("/{user_id}", response_model=UserDetail)
async def update_user(
    user_id: UUID,
    body: UserUpdate,
    _=require_permissions("users:write"),
    db: AsyncSession = Depends(get_db),
):
    """Update a user's email or active status. Requires users:write permission."""
    result = await db.execute(
        select(User).where(User.id == user_id).options(selectinload(User.roles))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundException("User not found")

    if body.email is not None:
        user.email = body.email
    if body.is_active is not None:
        user.is_active = body.is_active

    await db.flush()

    return UserDetail(
        id=user.id,
        email=user.email,
        is_active=user.is_active,
        oauth_provider=user.oauth_provider,
        created_at=user.created_at,
        updated_at=user.updated_at,
        roles=[r.name for r in user.roles],
    )


@router.put("/{user_id}/roles", status_code=status.HTTP_204_NO_CONTENT)
async def assign_roles(
    user_id: UUID,
    body: AssignRolesRequest,
    _=require_permissions("roles:manage"),
    db: AsyncSession = Depends(get_db),
):
    """Assign roles to a user. Replaces all current roles. Requires roles:manage permission."""
    result = await db.execute(
        select(User).where(User.id == user_id).options(selectinload(User.roles))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundException("User not found")

    roles_result = await db.execute(
        select(Role).where(Role.id.in_(body.role_ids))
    )
    roles = list(roles_result.scalars().all())

    if len(roles) != len(body.role_ids):
        raise HTTPException(status_code=400, detail="One or more role IDs are invalid")

    user.roles = roles
