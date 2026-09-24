"""Test RBAC endpoints."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_my_permissions(seeded_client: AsyncClient, auth_headers):
    resp = await seeded_client.get("/api/v1/roles/me/permissions", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_list_roles_requires_permission(seeded_client: AsyncClient, auth_headers):
    """Regular user should be forbidden from listing roles."""
    resp = await seeded_client.get("/api/v1/roles/", headers=auth_headers)
    assert resp.status_code == 403
