"""
Seed the database with default roles and permissions.
Run with: uv run python -m app.seeds.run
"""
import asyncio
from sqlalchemy import select
from app.database import async_session, engine, Base
from app.models.role import Role, Permission, role_permissions
from app.models.user import User
from app.models.refresh_token import RefreshToken

# Default permissions
DEFAULT_PERMISSIONS = [
    ("users:read", "Read user profiles"),
    ("users:write", "Create and update users"),
    ("roles:read", "View roles and permissions"),
    ("roles:manage", "Create, update, and delete roles"),
    ("orders:read", "Read orders (gateway)"),
    ("orders:write", "Create and update orders (gateway)"),
    ("products:read", "Read products (gateway)"),
    ("products:write", "Create and update products (gateway)"),
]

# Default roles and their permissions
DEFAULT_ROLES = {
    "superadmin": {
        "description": "Full access to everything",
        "permissions": [p[0] for p in DEFAULT_PERMISSIONS],  # all permissions
    },
    "admin": {
        "description": "Administrative access",
        "permissions": [
            "users:read", "users:write",
            "roles:read", "roles:manage",
            "orders:read", "orders:write",
            "products:read", "products:write",
        ],
    },
    "moderator": {
        "description": "Moderate users and content",
        "permissions": ["users:read", "orders:read", "products:read"],
    },
    "user": {
        "description": "Default role for new users",
        "permissions": ["orders:read", "products:read"],
    },
}


async def seed():
    # Create tables if they don't exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        # Seed permissions
        perm_map: dict[str, Permission] = {}
        for name, description in DEFAULT_PERMISSIONS:
            result = await session.execute(
                select(Permission).where(Permission.name == name)
            )
            perm = result.scalar_one_or_none()
            if not perm:
                perm = Permission(name=name, description=description)
                session.add(perm)
                await session.flush()
                print(f"  ✅ Created permission: {name}")
            else:
                print(f"  ⏭️  Permission exists: {name}")
            perm_map[name] = perm

        # Seed roles
        for role_name, role_data in DEFAULT_ROLES.items():
            result = await session.execute(
                select(Role).where(Role.name == role_name)
            )
            role = result.scalar_one_or_none()
            if not role:
                role = Role(name=role_name, description=role_data["description"])
                role.permissions = [perm_map[p] for p in role_data["permissions"]]
                session.add(role)
                await session.flush()
                print(f"  ✅ Created role: {role_name} ({len(role_data['permissions'])} permissions)")
            else:
                print(f"  ⏭️  Role exists: {role_name}")

        await session.commit()

    print("\n🌱 Seeding complete!")


if __name__ == "__main__":
    print("🌱 Seeding database...\n")
    asyncio.run(seed())
