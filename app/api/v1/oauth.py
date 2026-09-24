from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuth
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta, timezone

from app.database import get_db
from app.models.user import User
from app.models.role import Role
from app.models.refresh_token import RefreshToken
from app.schemas.auth import TokenResponse
from app.core.security import create_access_token, create_refresh_token, hash_token
from app.config import get_settings

router = APIRouter(prefix="/oauth", tags=["OAuth"])
settings = get_settings()

oauth = OAuth()

# ─── Register providers ──────────────────────────────────

if settings.GOOGLE_CLIENT_ID:
    oauth.register(
        name="google",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

if settings.GITHUB_CLIENT_ID:
    oauth.register(
        name="github",
        client_id=settings.GITHUB_CLIENT_ID,
        client_secret=settings.GITHUB_CLIENT_SECRET,
        authorize_url="https://github.com/login/oauth/authorize",
        access_token_url="https://github.com/login/oauth/access_token",
        api_base_url="https://api.github.com/",
        client_kwargs={"scope": "user:email"},
    )

if settings.DISCORD_CLIENT_ID:
    oauth.register(
        name="discord",
        client_id=settings.DISCORD_CLIENT_ID,
        client_secret=settings.DISCORD_CLIENT_SECRET,
        authorize_url="https://discord.com/api/oauth2/authorize",
        access_token_url="https://discord.com/api/oauth2/token",
        api_base_url="https://discord.com/api/v10/",
        client_kwargs={"scope": "identify email"},
    )

PROVIDERS = {"google", "github", "discord"}


def _get_provider(provider: str):
    if provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")
    client = oauth.create_client(provider)
    if client is None:
        raise HTTPException(
            status_code=400,
            detail=f"Provider '{provider}' is not configured. Set the client ID and secret in .env",
        )
    return client


async def _issue_tokens(user: User, db: AsyncSession) -> TokenResponse:
    role_names = [role.name for role in user.roles]
    access_token = create_access_token(user.id, role_names)
    refresh_token = create_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token(refresh_token),
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
    )
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.get("/{provider}/login")
async def oauth_login(provider: str, request: Request):
    """Redirect to the OAuth provider's authorization page."""
    client = _get_provider(provider)
    redirect_uri = f"{settings.OAUTH_REDIRECT_BASE_URL}/api/v1/oauth/{provider}/callback"
    return await client.authorize_redirect(request, redirect_uri)


@router.get("/{provider}/callback", response_model=TokenResponse)
async def oauth_callback(
    provider: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle OAuth callback, create/link user, issue tokens."""
    client = _get_provider(provider)
    token = await client.authorize_access_token(request)

    # Extract user info (provider-specific)
    email: str | None = None
    oauth_id: str | None = None

    if provider == "google":
        user_info = token.get("userinfo", {})
        email = user_info.get("email")
        oauth_id = user_info.get("sub")

    elif provider == "github":
        resp = await client.get("user", token=token)
        user_info = resp.json()
        email = user_info.get("email")
        oauth_id = str(user_info.get("id"))
        if not email:
            emails_resp = await client.get("user/emails", token=token)
            emails = emails_resp.json()
            primary = next((e for e in emails if e.get("primary")), None)
            email = primary["email"] if primary else None

    elif provider == "discord":
        resp = await client.get("users/@me", token=token)
        user_info = resp.json()
        email = user_info.get("email")
        oauth_id = user_info.get("id")

    if not email:
        raise HTTPException(status_code=400, detail="Could not retrieve email from provider")

    # Find or create user
    result = await db.execute(
        select(User).where(User.email == email).options(selectinload(User.roles))
    )
    user = result.scalar_one_or_none()

    if not user:
        user = User(email=email, oauth_provider=provider, oauth_id=oauth_id)
        db.add(user)
        await db.flush()

        # Assign default role
        default_role_result = await db.execute(select(Role).where(Role.name == "user"))
        default_role = default_role_result.scalar_one_or_none()
        if default_role:
            user.roles.append(default_role)
            await db.flush()

        # Re-fetch with roles loaded
        result = await db.execute(
            select(User).where(User.id == user.id).options(selectinload(User.roles))
        )
        user = result.scalar_one()

    elif not user.oauth_provider:
        # Link OAuth to existing email-registered account
        user.oauth_provider = provider
        user.oauth_id = oauth_id

    return await _issue_tokens(user, db)
