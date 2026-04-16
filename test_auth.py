import pytest


@pytest.mark.asyncio
async def test_register_success(client):
    response = await client.post("/api/v1/auth/register", json={
        "email": "newuser@example.com",
        "username": "newuser",
        "password": "password1234",
        "full_name": "New User",
        "disciplines": ["running"],
    })
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_register_duplicate_email(client, test_user):
    response = await client.post("/api/v1/auth/register", json={
        "email": test_user.email,
        "username": "differentuser",
        "password": "password1234",
    })
    assert response.status_code == 400
    assert "email" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_register_duplicate_username(client, test_user):
    response = await client.post("/api/v1/auth/register", json={
        "email": "another@example.com",
        "username": test_user.username,
        "password": "password1234",
    })
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_login_success(client, test_user):
    response = await client.post("/api/v1/auth/login", json={
        "email": test_user.email,
        "password": "securepassword123",
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data


@pytest.mark.asyncio
async def test_login_wrong_password(client, test_user):
    response = await client.post("/api/v1/auth/login", json={
        "email": test_user.email,
        "password": "wrongpassword",
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_email(client):
    response = await client.post("/api/v1/auth/login", json={
        "email": "ghost@example.com",
        "password": "password",
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me(client, auth_headers):
    response = await client.get("/api/v1/users/me", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "testuser"
    assert data["email"] == "testuser@example.com"


@pytest.mark.asyncio
async def test_get_me_unauthorized(client):
    response = await client.get("/api/v1/users/me")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_refresh_token(client, test_user):
    # Login to get tokens
    login_resp = await client.post("/api/v1/auth/login", json={
        "email": test_user.email,
        "password": "securepassword123",
    })
    refresh_token = login_resp.json()["refresh_token"]

    # Use refresh token
    response = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["refresh_token"] != refresh_token  # Rotated


@pytest.mark.asyncio
async def test_change_password(client, auth_headers):
    response = await client.post(
        "/api/v1/auth/change-password",
        headers=auth_headers,
        json={
            "current_password": "securepassword123",
            "new_password": "newpassword456",
        },
    )
    assert response.status_code == 204
