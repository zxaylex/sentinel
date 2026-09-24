
import os
from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database import Base, get_db
from app.main import app

# Use DATABASE_URL from environment (CI provides Postgres), fall back for local dev
TEST_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://sentinel:sentinelpassword@localhost:5432/sentinel_test",
)

engine_test = create_async_engine(TEST_DATABASE_URL, echo=False)
async_session_test = async_sessionmaker(
    engine_test, class_=AsyncSession, expire_on_commit=False
)


@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    """Create tables before each test and drop after."""
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_test() as session:
        yield session


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Provide an async test client with a fresh DB session per request."""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with async_session_test() as session:
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
async def seeded_db(db_session: AsyncSession):
    """Seed the test DB with default roles and permissions."""
    from app.models.role import Permission, Role

    perms = {}
    for name in ["users:read", "users:write", "roles:read", "roles:manage"]:
        p = Permission(name=name, description=f"Test permission: {name}")
        db_session.add(p)
        perms[name] = p
    await db_session.flush()

    user_role = Role(name="user", description="Default role")
    user_role.permissions = []
    db_session.add(user_role)

    admin_role = Role(name="admin", description="Admin role")
    admin_role.permissions = list(perms.values())
    db_session.add(admin_role)

    superadmin_role = Role(name="superadmin", description="Superadmin role")
    superadmin_role.permissions = list(perms.values())
    db_session.add(superadmin_role)

    await db_session.commit()
    return {"roles": {"user": user_role, "admin": admin_role}, "permissions": perms}


@pytest_asyncio.fixture
async def seeded_client(seeded_db) -> AsyncGenerator[AsyncClient, None]:
    """Client with seeded DB � use this when tests need roles/permissions."""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with async_session_test() as session:
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
