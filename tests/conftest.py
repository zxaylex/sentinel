"""Shared test fixtures."""
import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database import Base, get_db
from app.main import app

TEST_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+[REDACTED_CONN_STRING]://localhost:5432/sentinel_test",
)


@pytest_asyncio.fixture
async def engine():
    """Create a fresh engine per test to avoid cross-loop issues."""
    eng = create_async_engine(TEST_DATABASE_URL, echo=False, pool_size=5, max_overflow=0)

    # Create all tables
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield eng

    # Drop all tables + dispose
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def client(engine, session_factory) -> AsyncGenerator[AsyncClient, None]:
    """Test client with fresh DB session per request."""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    app.state.redis = None

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def seeded_client(engine, session_factory) -> AsyncGenerator[AsyncClient, None]:
    """Client with seeded roles and permissions."""
    from app.models.role import Role, Permission

    # Seed data
    async with session_factory() as session:
        perms = {}
        for name in ["users:read", "users:write", "roles:read", "roles:manage"]:
            p = Permission(name=name, description=f"Test permission: {name}")
            session.add(p)
            perms[name] = p
        await session.flush()

        user_role = Role(name="user", description="Default role")
        user_role.permissions = []
        session.add(user_role)

        admin_role = Role(name="admin", description="Admin role")
        admin_role.permissions = list(perms.values())
        session.add(admin_role)

        superadmin_role = Role(name="superadmin", description="Superadmin role")
        superadmin_role.permissions = list(perms.values())
        session.add(superadmin_role)

        await session.commit()

    # Now create the client
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    app.state.redis = None

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def auth_headers(seeded_client: AsyncClient) -> dict[str, str]:
    """Register a test user and return auth headers."""
    await seeded_client.post(
        "/api/v1/auth/register",
        json={"email": "test@example.com", "password": "testpassword123"},
    )
    resp = await seeded_client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "testpassword123"},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
