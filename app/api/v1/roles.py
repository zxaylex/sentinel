from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from uuid import UUID

from app.database import get_db
from app.models.role import Role, Permission
from app.models.user import User
from app.schemas.role import (
    RoleCreate,
    RoleUpdate,
    RoleResponse,
    PermissionResponse,
    AssignRolesRequest,
)
from app.core.rbac import require_permissions
from app.core.exceptions import ConflictException, NotFoundException
from app.middleware.auth_middleware import get_current_user_id

router = APIRouter(prefix="/roles", tags=["RBAC"])


@router.get("/", response_model=list[RoleResponse])
async def list_roles(
    _=require_permissions("roles:read"),
    db: AsyncSession = Depends(get_db),
):
    """List all roles with their permissions."""
    result = await db.execute(select(Role).options(selectinload(Role.permissions)))
    return result.scalars().all()


@router.post("/", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role(
    body: RoleCreate,
    _=require_permissions("roles:manage"),
    db: AsyncSession = Depends(get_db),
):
    """Create a custom role with optional permissions."""
    # Check for duplicate name
    existing = await db.execute(select(Role).where(Role.name == body.name))
    if existing.scalar_one_or_none():
        raise ConflictException(f"Role '{body.name}' already exists")

    role = Role(name=body.name, description=body.description)

    if body.permission_ids:
        result = await db.execute(
            select(Permission).where(Permission.id.in_(body.permission_ids))
        )
        role.permissions = list(result.scalars().all())

    db.add(role)
    await db.flush()

    # Re-fetch with permissions loaded
    result = await db.execute(
        select(Role).where(Role.id == role.id).options(selectinload(Role.permissions))
    )
    return result.scalar_one()


@router.put("/{role_id}", response_model=RoleResponse)
async def update_role(
    role_id: UUID,
    body: RoleUpdate,
    _=require_permissions("roles:manage"),
    db: AsyncSession = Depends(get_db),
):
    """Update a role's name, description, or permissions."""
    result = await db.execute(
        select(Role).where(Role.id == role_id).options(selectinload(Role.permissions))
    )
    role = result.scalar_one_or_none()
    if not role:
        raise NotFoundException("Role not found")

    if body.name is not None:
        role.name = body.name
    if body.description is not None:
        role.description = body.description
    if body.permission_ids is not None:
        perms_result = await db.execute(
            select(Permission).where(Permission.id.in_(body.permission_ids))
        )
        role.permissions = list(perms_result.scalars().all())

    await db.flush()
    return role


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: UUID,
    _=require_permissions("roles:manage"),
    db: AsyncSession = Depends(get_db),
):
    """Delete a role."""
    result = await db.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()
    if not role:
        raise NotFoundException("Role not found")
    if role.name in {"superadmin", "admin", "moderator", "user"}:
        raise HTTPException(status_code=400, detail="Cannot delete built-in roles")
    await db.delete(role)


@router.get("/permissions", response_model=list[PermissionResponse])
async def list_permissions(
    _=require_permissions("roles:read"),
    db: AsyncSession = Depends(get_db),
):
    """List all available permissions."""
    result = await db.execute(select(Permission))
    return result.scalars().all()


@router.get("/me/permissions", response_model=list[str])
async def my_permissions(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get the current user's effective permissions from all assigned roles."""
    result = await db.execute(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.roles).selectinload(Role.permissions))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundException("User not found")

    permissions: set[str] = set()
    for role in user.roles:
        for perm in role.permissions:
            permissions.add(perm.name)
    return sorted(permissions)
