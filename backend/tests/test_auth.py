"""Automated tests for Supabase JWT verification and /api/v1/auth/me endpoint."""

import time
import uuid
import pytest
import jwt
from fastapi.testclient import TestClient
from app.core.config import settings
from app.main import app

client = TestClient(app)

TEST_JWT_SECRET = "super-secret-test-key-for-supabase-jwt-verification-unit-tests"


@pytest.fixture(autouse=True)
def setup_jwt_secret(monkeypatch):
    """Ensure test JWT secret is configured in application settings for test runs."""
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", TEST_JWT_SECRET)


def create_test_token(
    user_id: str,
    email: str = "user@example.com",
    role: str = "authenticated",
    aud: str = "authenticated",
    exp_offset: int = 3600,
    secret: str = TEST_JWT_SECRET,
    metadata: dict = None,
) -> str:
    """Generate a signed JWT token for test requests."""
    now = int(time.time())
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "aud": aud,
        "iat": now,
        "exp": now + exp_offset,
        "app_metadata": {"provider": "email"},
        "user_metadata": metadata or {"full_name": "Test User"},
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def test_unauthenticated_request_rejected():
    """Verify that requests missing the Authorization header return HTTP 401."""
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert "Missing or invalid authentication credentials" in response.json()["detail"]


def test_malformed_token_rejected():
    """Verify that invalid / garbage tokens return HTTP 401."""
    headers = {"Authorization": "Bearer not-a-valid-jwt-token"}
    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 401
    assert "Invalid authentication token" in response.json()["detail"]


def test_expired_token_rejected():
    """Verify that expired JWTs return HTTP 401 with expiration error."""
    expired_token = create_test_token(
        user_id=str(uuid.uuid4()),
        exp_offset=-300,  # Expired 5 minutes ago
    )
    headers = {"Authorization": f"Bearer {expired_token}"}
    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 401
    assert "token has expired" in response.json()["detail"].lower()


def test_incorrectly_signed_token_rejected():
    """Verify that tokens signed with an untrusted secret key return HTTP 401."""
    tampered_token = create_test_token(
        user_id=str(uuid.uuid4()),
        secret="different-untrusted-signing-secret",
    )
    headers = {"Authorization": f"Bearer {tampered_token}"}
    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 401


def test_missing_sub_claim_rejected():
    """Verify that tokens without a user subject claim ('sub') are rejected."""
    now = int(time.time())
    payload = {
        "email": "nosub@example.com",
        "aud": "authenticated",
        "exp": now + 3600,
    }
    token = jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 401
    assert "missing subject claim" in response.json()["detail"].lower()


def test_valid_authenticated_request_returns_profile():
    """Verify that a valid authenticated JWT returns the user's profile."""
    user_id = str(uuid.uuid4())
    test_email = "solomon@auren.ai"
    test_name = "Solomon Yamal"

    token = create_test_token(
        user_id=user_id,
        email=test_email,
        metadata={"full_name": test_name},
    )

    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/api/v1/auth/me", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == user_id
    assert data["email"] == test_email
    assert data["full_name"] == test_name
    assert data["role"] == "authenticated"


def test_strict_user_isolation_between_accounts():
    """Verify that User A's token cannot return User B's profile identity."""
    user_a_id = str(uuid.uuid4())
    user_b_id = str(uuid.uuid4())

    token_a = create_test_token(user_id=user_a_id, email="user_a@auren.ai", metadata={"full_name": "User A"})
    token_b = create_test_token(user_id=user_b_id, email="user_b@auren.ai", metadata={"full_name": "User B"})

    res_a = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_a}"})
    assert res_a.status_code == 200
    assert res_a.json()["id"] == user_a_id
    assert res_a.json()["id"] != user_b_id

    res_b = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_b}"})
    assert res_b.status_code == 200
    assert res_b.json()["id"] == user_b_id
    assert res_b.json()["id"] != user_a_id

