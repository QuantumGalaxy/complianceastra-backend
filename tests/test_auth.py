"""
Technical test cases: Authentication flow (AUTH-1 through AUTH-6)
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_auth_1_register_valid_user(client: AsyncClient):
    """AUTH-1: Register valid user returns 200 with access_token and user."""
    response = await client.post(
        "/api/auth/register",
        json={
            "email": "newuser@example.com",
            "password": "securepassword123",
            "full_name": "New User",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "newuser@example.com"
    assert data["user"]["full_name"] == "New User"


@pytest.mark.asyncio
async def test_auth_2_register_duplicate_email(client: AsyncClient):
    """AUTH-2: Register with existing email returns 400."""
    await client.post(
        "/api/auth/register",
        json={"email": "dup@example.com", "password": "password123"},
    )
    response = await client.post(
        "/api/auth/register",
        json={"email": "dup@example.com", "password": "otherpass"},
    )
    assert response.status_code == 400
    assert "already" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_auth_3_login_valid_user(client: AsyncClient):
    """AUTH-3: Login with valid credentials returns 200 with token."""
    await client.post(
        "/api/auth/register",
        json={"email": "login@example.com", "password": "mypassword"},
    )
    response = await client.post(
        "/api/auth/login",
        json={"email": "login@example.com", "password": "mypassword"},
    )
    assert response.status_code == 200
    assert "access_token" in response.json()


@pytest.mark.asyncio
async def test_auth_4_login_invalid_credentials(client: AsyncClient):
    """AUTH-4: Login with wrong password returns 401."""
    await client.post(
        "/api/auth/register",
        json={"email": "wrong@example.com", "password": "correct"},
    )
    response = await client.post(
        "/api/auth/login",
        json={"email": "wrong@example.com", "password": "wrong"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_auth_5_me_with_valid_token(client: AsyncClient, auth_headers: dict):
    """AUTH-5: GET /me with valid token returns user."""
    response = await client.get("/api/auth/me", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["email"] == "test@example.com"


@pytest.mark.asyncio
async def test_auth_6_me_without_token(client: AsyncClient):
    """AUTH-6: GET /me without token returns 401."""
    response = await client.get("/api/auth/me")
    assert response.status_code == 401
