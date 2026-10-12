"""Tests for Authentication, Password Security, and Token Lifecycle."""

from datetime import timedelta
import pytest
from app.core.security import create_access_token


def test_registration_success(client):
    payload = {
        "email": "merchant@brand.in",
        "password": "StrongPassword123!",
        "full_name": "Rohan Sharma",
        "organization_name": "Royal Loom D2C",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0


def test_registration_duplicate_email_fails(client):
    payload = {
        "email": "duplicate@brand.in",
        "password": "StrongPassword123!",
        "organization_name": "Brand A",
    }
    client.post("/api/v1/auth/register", json=payload)
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]


def test_login_success(client, create_user):
    create_user(email="login@brand.in", password="ValidPassword123!")

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "login@brand.in", "password": "ValidPassword123!"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


def test_login_invalid_password_fails(client, create_user):
    create_user(email="login@brand.in", password="ValidPassword123!")

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "login@brand.in", "password": "WrongPassword!"},
    )
    assert response.status_code == 401
    assert "Incorrect email or password" in response.json()["detail"]


def test_login_inactive_user_fails(client, create_user):
    create_user(email="inactive@brand.in", password="Password123!", is_active=False)

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "inactive@brand.in", "password": "Password123!"},
    )
    assert response.status_code == 403
    assert "inactive" in response.json()["detail"].lower()


def test_token_refresh_lifecycle(client):
    # Register to get initial tokens
    reg_resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": "refresher@brand.in",
            "password": "Password123!",
            "organization_name": "Refresh Store",
        },
    )
    refresh_token = reg_resp.json()["refresh_token"]

    # Use refresh token
    ref_resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert ref_resp.status_code == 200
    new_data = ref_resp.json()
    assert "access_token" in new_data
    assert "refresh_token" in new_data
    new_refresh_token = new_data["refresh_token"]

    # Reusing the old rotated refresh token MUST be rejected
    reuse_resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert reuse_resp.status_code == 401
    assert "revoked" in reuse_resp.json()["detail"].lower()


def test_logout_revokes_token(client, create_user, auth_headers):
    user = create_user(email="logout@brand.in", password="Password123!")
    headers = auth_headers(user)

    # Access endpoint before logout
    me_resp1 = client.get("/api/v1/auth/me", headers=headers)
    assert me_resp1.status_code == 200

    # Logout
    logout_resp = client.post("/api/v1/auth/logout", headers=headers)
    assert logout_resp.status_code == 200

    # Subsequent access with same token is revoked
    me_resp2 = client.get("/api/v1/auth/me", headers=headers)
    assert me_resp2.status_code == 401
    assert "revoked" in me_resp2.json()["detail"].lower()


def test_expired_token_rejected(client, create_user):
    user = create_user(email="expired@brand.in")
    expired_token = create_access_token(subject=str(user.id), expires_delta=timedelta(seconds=-10))

    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert response.status_code == 401
    assert "expired" in response.json()["detail"].lower()
