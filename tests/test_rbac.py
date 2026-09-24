"""Test RBAC endpoints."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_my_permissions_as_regular_user(client: AsyncClient, auth_headers):
    resp = await client.get("/api/v1/roles/me/permissions", headers=auth_headers)
    assert resp.status_code == 200
    # Regular "user" role has limited permissions
    data = resp.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_list_roles_requires_permission(client: AsyncClient, auth_headers):
    """Regular user should be forbidden from listing roles."""
    resp = await client.get("/api/v1/roles/", headers=auth_headers)
    # Should be 403 — "user" role doesn't have "roles:read"
    assert resp.status_code == 403
