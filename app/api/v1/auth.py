from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.core.exceptions import ConflictException, CredentialsException
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.database import get_db
from app.middleware.auth_middleware import get_current_user_id
from app.models.refresh_token import RefreshToken
from app.models.role import Role
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["Auth"])
settings = get_settings()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Create a new user account with email and password."""
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise ConflictException("Email already registered")

    user = User(email=body.email, password_hash=hash_password(body.password))
    db.add(user)
    await db.flush()

    # Assign default "user" role
    default_role = await db.execute(select(Role).where(Role.name == "user"))
    role = default_role.scalar_one_or_none()
    if role:
        user.roles.append(role)
        await db.flush()

    return UserResponse(
        id=user.id,
        email=user.email,
        is_active=user.is_active,
        oauth_provider=user.oauth_provider,
        roles=[r.name for r in user.roles],
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate with email and password. Returns access + refresh tokens."""
    result = await db.execute(
        select(User).where(User.email == body.email).options(selectinload(User.roles))
    )
    user = result.scalar_one_or_none()

    if not user or not user.password_hash or not verify_password(body.password, user.password_hash):
        raise CredentialsException("Invalid email or password")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    role_names = [role.name for role in user.roles]
    access_token = create_access_token(user.id, role_names)
    refresh_token = create_refresh_token()

    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token(refresh_token),
            expires_at=datetime.now(UTC)
            + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
    )

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Rotate refresh token and issue a new access token."""
    token_hash = hash_token(body.refresh_token)
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked.is_(False),
            RefreshToken.expires_at > datetime.now(UTC),
        )
    )
    stored_token = result.scalar_one_or_none()

    if not stored_token:
        raise CredentialsException("Invalid or expired refresh token")

    # Revoke old token (rotation)
    stored_token.revoked = True

    # Fetch user and roles
    user_result = await db.execute(
        select(User).where(User.id == stored_token.user_id).options(selectinload(User.roles))
    )
    user = user_result.scalar_one()
    role_names = [role.name for role in user.roles]

    # Issue new token pair
    new_access = create_access_token(user.id, role_names)
    new_refresh = create_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token(new_refresh),
            expires_at=datetime.now(UTC)
            + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
    )

    return TokenResponse(access_token=new_access, refresh_token=new_refresh)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    body: RefreshRequest,
    request: Request,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a refresh token. Optionally blacklists the access token via Redis."""
    token_hash = hash_token(body.refresh_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    stored_token = result.scalar_one_or_none()
    if stored_token:
        stored_token.revoked = True

    # Blacklist the current access token in Redis
    redis = getattr(request.app.state, "redis", None)
    if redis:
        # Blacklist for the remaining TTL of the access token
        await redis.setex(
            f"blacklist:{request.headers.get('authorization', '').replace('Bearer ', '')}",
            settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "1",
        )
