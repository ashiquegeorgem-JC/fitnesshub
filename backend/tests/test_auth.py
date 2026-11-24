"""
Phase 2 Authentication & Owner Security Tests — Regal Fitness Backend
======================================================================
Covers:
  - Owner login with phone + password (Argon2id)
  - Rate limiting on login attempts
  - Generic authentication failure responses
  - JWT access token validation, expiry, and malformed token handling
  - Refresh token rotation and replay/reuse detection
  - Session lifecycle: creation, listing, single logout, logout-all, revocation
  - Forgot password SMS OTP: generation, HMAC storage, cooldown, attempt limits, expiration
  - Password reset with complexity enforcement, session revocation, and old password rejection
  - Equal root permissions for both gym owners
  - Authentication audit ledger integrity (no plain secrets logged)
"""

import uuid
from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.config import settings
from app.core.rate_limit import limiter
from app.core.security import (
    create_access_token,
    create_password_reset_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.database.base import Base
from app.main import app
from app.models.audit import AuditLog
from app.models.owner import Owner, OwnerPasswordResetOTP, OwnerSession
from app.services.sms import mock_sms_provider


# ---------------------------------------------------------------------------
# Test Fixtures (SQLite in-memory with StaticPool for cross-thread sharing)
# ---------------------------------------------------------------------------


@pytest.fixture
def test_db():
    """Isolated in-memory SQLite database per test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def auth_client(test_db: Session):
    """TestClient wired to the test SQLite database session."""
    limiter.clear()
    mock_sms_provider.clear()

    def override_get_db():
        try:
            yield test_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def seed_owners(test_db: Session):
    """Seed the two official gym co-owners with Argon2id hashed passwords."""
    owner1 = Owner(
        id=uuid.uuid4(),
        name="Owner One",
        phone_number="+919876543210",
        email="owner1@regalfitness.com",
        password_hash=hash_password("OwnerPassword123!"),
        account_status="active",
    )
    owner2 = Owner(
        id=uuid.uuid4(),
        name="Owner Two",
        phone_number="+919876543211",
        email="owner2@regalfitness.com",
        password_hash=hash_password("OwnerPassword456!"),
        account_status="active",
    )
    test_db.add_all([owner1, owner2])
    test_db.commit()
    return owner1, owner2


# ---------------------------------------------------------------------------
# 1. Owner Login Tests
# ---------------------------------------------------------------------------


class TestOwnerLogin:
    def test_login_success(self, auth_client: TestClient, seed_owners, test_db: Session):
        owner1, _ = seed_owners
        resp = auth_client.post(
            "/api/v1/auth/login",
            json={
                "phone_number": "+919876543210",
                "password": "OwnerPassword123!",
                "device_info": "Chrome / Windows 11",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"
        assert body["expires_in"] == settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60

        # Verify session record in DB
        session = test_db.execute(
            select(OwnerSession).where(OwnerSession.owner_id == owner1.id)
        ).scalar_one_or_none()
        assert session is not None
        assert session.is_revoked is False
        assert session.device_info == "Chrome / Windows 11"

        # Verify audit log
        audit = test_db.execute(
            select(AuditLog).where(
                AuditLog.owner_id == owner1.id, AuditLog.action == "LOGIN_SUCCESS"
            )
        ).scalar_one_or_none()
        assert audit is not None
        assert audit.entity_type == "owner_session"

    def test_login_incorrect_password(self, auth_client: TestClient, seed_owners, test_db: Session):
        resp = auth_client.post(
            "/api/v1/auth/login",
            json={
                "phone_number": "+919876543210",
                "password": "WrongPassword!",
            },
        )
        assert resp.status_code == 401
        body = resp.json()
        assert body["error"]["code"] == "UNAUTHORIZED"
        assert "Invalid phone number or password" in body["error"]["message"]

        # Audit log for failed login
        audit = test_db.execute(
            select(AuditLog).where(AuditLog.action == "LOGIN_FAILED")
        ).scalar_one_or_none()
        assert audit is not None

    def test_login_unknown_phone_number(self, auth_client: TestClient, seed_owners):
        resp = auth_client.post(
            "/api/v1/auth/login",
            json={
                "phone_number": "+919000000000",
                "password": "AnyPassword123!",
            },
        )
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "UNAUTHORIZED"
        # Generic message: does not reveal whether phone exists
        assert "Invalid phone number or password" in resp.json()["error"]["message"]

    def test_login_missing_credentials(self, auth_client: TestClient):
        resp = auth_client.post("/api/v1/auth/login", json={})
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_login_rate_limiting(self, auth_client: TestClient, seed_owners):
        phone = "+919876543210"
        # 5 failed attempts allowed
        for _ in range(settings.LOGIN_RATE_LIMIT_MAX_ATTEMPTS):
            resp = auth_client.post(
                "/api/v1/auth/login",
                json={"phone_number": phone, "password": "WrongPassword!"},
            )
            assert resp.status_code == 401

        # 6th attempt should be blocked by rate limiter
        resp = auth_client.post(
            "/api/v1/auth/login",
            json={"phone_number": phone, "password": "OwnerPassword123!"},
        )
        assert resp.status_code == 429
        assert resp.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"
        assert "Too many login attempts" in resp.json()["error"]["message"]


# ---------------------------------------------------------------------------
# 2. Token Validation & Protected Routes
# ---------------------------------------------------------------------------


class TestTokenValidation:
    def test_access_token_validation(self, auth_client: TestClient, seed_owners):
        # Login
        login_resp = auth_client.post(
            "/api/v1/auth/login",
            json={"phone_number": "+919876543210", "password": "OwnerPassword123!"},
        )
        token = login_resp.json()["access_token"]

        # Call /me
        resp = auth_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "Owner One"
        assert body["phone_number"] == "+919876543210"
        assert body["account_status"] == "active"

    def test_expired_access_token(self, auth_client: TestClient, seed_owners, test_db: Session):
        owner1, _ = seed_owners
        session_id = uuid.uuid4()
        session = OwnerSession(
            id=session_id,
            owner_id=owner1.id,
            refresh_token_hash="dummy_hash",
            is_revoked=False,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        test_db.add(session)
        test_db.commit()

        # Create expired token (-10 minutes)
        expired_token = create_access_token(
            owner1.id, session_id, expires_delta=timedelta(minutes=-10)
        )

        resp = auth_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert resp.status_code == 401
        assert "expired" in resp.json()["error"]["message"].lower()

    def test_invalid_access_token(self, auth_client: TestClient):
        resp = auth_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer not-a-valid-jwt-token"},
        )
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "UNAUTHORIZED"

    def test_protected_route_without_auth(self, auth_client: TestClient):
        resp = auth_client.get("/api/v1/auth/me")
        # FastAPI HTTPBearer returns 401 or 403 when header missing
        assert resp.status_code in (401, 403)

    def test_refresh_token_rejected_on_access_route(self, auth_client: TestClient, seed_owners):
        login_resp = auth_client.post(
            "/api/v1/auth/login",
            json={"phone_number": "+919876543210", "password": "OwnerPassword123!"},
        )
        refresh_token = login_resp.json()["refresh_token"]

        # Presenting refresh_token on an access route must fail
        resp = auth_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {refresh_token}"},
        )
        assert resp.status_code == 401
        assert "Invalid token type" in resp.json()["error"]["message"]


# ---------------------------------------------------------------------------
# 3. Refresh Token Rotation & Reuse Detection
# ---------------------------------------------------------------------------


class TestTokenRefreshAndRotation:
    def test_successful_refresh_and_rotation(self, auth_client: TestClient, seed_owners, test_db: Session):
        login_resp = auth_client.post(
            "/api/v1/auth/login",
            json={"phone_number": "+919876543210", "password": "OwnerPassword123!"},
        )
        old_access = login_resp.json()["access_token"]
        old_refresh = login_resp.json()["refresh_token"]

        # Perform refresh
        refresh_resp = auth_client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": old_refresh},
        )
        assert refresh_resp.status_code == 200
        new_tokens = refresh_resp.json()
        new_access = new_tokens["access_token"]
        new_refresh = new_tokens["refresh_token"]

        # Refresh tokens must be rotated (different)
        assert new_refresh != old_refresh
        assert new_access != old_access

        # New access token must work on /me
        me_resp = auth_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {new_access}"},
        )
        assert me_resp.status_code == 200

    def test_old_refresh_token_rejected(self, auth_client: TestClient, seed_owners):
        login_resp = auth_client.post(
            "/api/v1/auth/login",
            json={"phone_number": "+919876543210", "password": "OwnerPassword123!"},
        )
        old_refresh = login_resp.json()["refresh_token"]

        # First refresh succeeds
        auth_client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})

        # Second refresh using old token must be rejected
        second_resp = auth_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": old_refresh}
        )
        assert second_resp.status_code == 401
        assert "reuse" in second_resp.json()["error"]["message"].lower()

    def test_refresh_token_reuse_detection_revokes_all_sessions(
        self, auth_client: TestClient, seed_owners, test_db: Session
    ):
        owner1, _ = seed_owners
        # Login from device A
        login_a = auth_client.post(
            "/api/v1/auth/login",
            json={"phone_number": "+919876543210", "password": "OwnerPassword123!"},
        ).json()

        # Login from device B
        login_b = auth_client.post(
            "/api/v1/auth/login",
            json={"phone_number": "+919876543210", "password": "OwnerPassword123!"},
        ).json()

        # Device A refreshes once
        refresh_a = auth_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": login_a["refresh_token"]}
        ).json()

        # Attacker replays old Device A refresh token
        replay_resp = auth_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": login_a["refresh_token"]}
        )
        assert replay_resp.status_code == 401
        assert "Token reuse detected" in replay_resp.json()["error"]["message"]

        # All sessions for owner1 must now be revoked
        active_sessions = test_db.execute(
            select(OwnerSession).where(
                OwnerSession.owner_id == owner1.id,
                OwnerSession.is_revoked.is_(False),
            )
        ).scalars().all()
        assert len(active_sessions) == 0

        # Audit log for reuse detection
        audit = test_db.execute(
            select(AuditLog).where(
                AuditLog.action == "REFRESH_TOKEN_REUSE_DETECTED"
            )
        ).scalar_one_or_none()
        assert audit is not None


# ---------------------------------------------------------------------------
# 4. Session Management & Logout
# ---------------------------------------------------------------------------


class TestSessionManagement:
    def test_logout_current_session(self, auth_client: TestClient, seed_owners, test_db: Session):
        login_resp = auth_client.post(
            "/api/v1/auth/login",
            json={"phone_number": "+919876543210", "password": "OwnerPassword123!"},
        ).json()
        token = login_resp["access_token"]

        # Logout
        logout_resp = auth_client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert logout_resp.status_code == 200
        assert "logged out" in logout_resp.json()["message"].lower()

        # Using same token on /me must now be rejected
        me_resp = auth_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me_resp.status_code == 401
        assert "revoked" in me_resp.json()["error"]["message"].lower()

    def test_logout_all_sessions(self, auth_client: TestClient, seed_owners):
        # Create 2 sessions
        login1 = auth_client.post(
            "/api/v1/auth/login",
            json={"phone_number": "+919876543210", "password": "OwnerPassword123!"},
        ).json()
        login2 = auth_client.post(
            "/api/v1/auth/login",
            json={"phone_number": "+919876543210", "password": "OwnerPassword123!"},
        ).json()

        # Logout all from session 2
        resp = auth_client.post(
            "/api/v1/auth/logout-all",
            headers={"Authorization": f"Bearer {login2['access_token']}"},
        )
        assert resp.status_code == 200

        # Both tokens must now be rejected
        assert auth_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {login1['access_token']}"},
        ).status_code == 401
        assert auth_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {login2['access_token']}"},
        ).status_code == 401

    def test_list_and_revoke_specific_session(self, auth_client: TestClient, seed_owners):
        login1 = auth_client.post(
            "/api/v1/auth/login",
            json={"phone_number": "+919876543210", "password": "OwnerPassword123!"},
        ).json()
        login2 = auth_client.post(
            "/api/v1/auth/login",
            json={"phone_number": "+919876543210", "password": "OwnerPassword123!"},
        ).json()

        # List sessions
        sessions_resp = auth_client.get(
            "/api/v1/auth/sessions",
            headers={"Authorization": f"Bearer {login2['access_token']}"},
        )
        assert sessions_resp.status_code == 200
        sessions = sessions_resp.json()
        assert len(sessions) == 2

        # Exactly one session is flagged as current
        current_count = sum(1 for s in sessions if s["is_current"])
        assert current_count == 1

        # Revoke session 1 specifically from session 2
        session1_id = [s["id"] for s in sessions if not s["is_current"]][0]
        revoke_resp = auth_client.delete(
            f"/api/v1/auth/sessions/{session1_id}",
            headers={"Authorization": f"Bearer {login2['access_token']}"},
        )
        assert revoke_resp.status_code == 200

        # Session 1 should now be rejected
        assert auth_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {login1['access_token']}"},
        ).status_code == 401

        # Session 2 must still be active
        assert auth_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {login2['access_token']}"},
        ).status_code == 200


# ---------------------------------------------------------------------------
# 5. Forgot Password SMS OTP Workflow
# ---------------------------------------------------------------------------


class TestForgotPasswordOTPWorkflow:
    def test_otp_generation_and_sms_dispatch(self, auth_client: TestClient, seed_owners, test_db: Session):
        owner1, _ = seed_owners
        phone = "+919876543210"

        resp = auth_client.post(
            "/api/v1/auth/forgot-password",
            json={"phone_number": phone},
        )
        assert resp.status_code == 200
        assert "dispatched" in resp.json()["message"].lower()

        # Verify SMS mock provider received the OTP
        assert len(mock_sms_provider.sent_messages) == 1
        msg = mock_sms_provider.sent_messages[0]
        assert msg["phone_number"] == phone
        otp = msg["otp"]
        assert len(otp) == 6
        assert otp.isdigit()

        # Verify raw OTP is NOT stored in the database (only HMAC)
        otp_rec = test_db.execute(
            select(OwnerPasswordResetOTP).where(
                OwnerPasswordResetOTP.owner_id == owner1.id
            )
        ).scalar_one()
        assert otp_rec.otp_hmac != otp
        assert len(otp_rec.otp_hmac) == 64  # SHA-256 hex string

    def test_otp_request_unknown_phone_returns_generic_message(
        self, auth_client: TestClient, seed_owners
    ):
        resp = auth_client.post(
            "/api/v1/auth/forgot-password",
            json={"phone_number": "+919000000000"},
        )
        # Returns 200 with generic message; no SMS sent
        assert resp.status_code == 200
        assert "dispatched" in resp.json()["message"].lower()
        assert len(mock_sms_provider.sent_messages) == 0

    def test_otp_resend_cooldown_enforced(self, auth_client: TestClient, seed_owners):
        phone = "+919876543210"
        # First request succeeds
        resp1 = auth_client.post(
            "/api/v1/auth/forgot-password", json={"phone_number": phone}
        )
        assert resp1.status_code == 200

        # Immediate second request must be blocked by cooldown (60 seconds)
        resp2 = auth_client.post(
            "/api/v1/auth/forgot-password", json={"phone_number": phone}
        )
        assert resp2.status_code == 429
        assert "cooldown" in resp2.json()["error"]["message"].lower() or "wait" in resp2.json()["error"]["message"].lower()

    def test_otp_verification_success(self, auth_client: TestClient, seed_owners):
        phone = "+919876543210"
        auth_client.post("/api/v1/auth/forgot-password", json={"phone_number": phone})
        otp = mock_sms_provider.get_last_otp(phone)

        resp = auth_client.post(
            "/api/v1/auth/verify-otp",
            json={"phone_number": phone, "otp": otp},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "reset_token" in body
        # Validate reset_token payload
        payload = decode_token(body["reset_token"], expected_type="password_reset")
        assert "otp_id" in payload

    def test_otp_verification_incorrect_code(self, auth_client: TestClient, seed_owners):
        phone = "+919876543210"
        auth_client.post("/api/v1/auth/forgot-password", json={"phone_number": phone})

        resp = auth_client.post(
            "/api/v1/auth/verify-otp",
            json={"phone_number": phone, "otp": "000000"},
        )
        assert resp.status_code == 400
        assert "2 attempt(s) remaining" in resp.json()["error"]["message"]

    def test_otp_attempt_limit_exceeded(self, auth_client: TestClient, seed_owners):
        phone = "+919876543210"
        auth_client.post("/api/v1/auth/forgot-password", json={"phone_number": phone})
        correct_otp = mock_sms_provider.get_last_otp(phone)

        # Fail 3 attempts
        for _ in range(3):
            auth_client.post(
                "/api/v1/auth/verify-otp",
                json={"phone_number": phone, "otp": "999999"},
            )

        # 4th attempt with correct OTP must now be rejected
        resp = auth_client.post(
            "/api/v1/auth/verify-otp",
            json={"phone_number": phone, "otp": correct_otp},
        )
        assert resp.status_code == 400
        assert "Maximum verification attempts exceeded" in resp.json()["error"]["message"]

    def test_expired_otp_rejected(self, auth_client: TestClient, seed_owners, test_db: Session):
        owner1, _ = seed_owners
        phone = "+919876543210"
        auth_client.post("/api/v1/auth/forgot-password", json={"phone_number": phone})
        otp = mock_sms_provider.get_last_otp(phone)

        # Manually expire the OTP in the database
        otp_rec = test_db.execute(
            select(OwnerPasswordResetOTP).where(
                OwnerPasswordResetOTP.owner_id == owner1.id
            )
        ).scalar_one()
        otp_rec.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        test_db.commit()

        resp = auth_client.post(
            "/api/v1/auth/verify-otp",
            json={"phone_number": phone, "otp": otp},
        )
        assert resp.status_code == 400
        assert "expired" in resp.json()["error"]["message"].lower()

    def test_complete_password_reset_workflow(self, auth_client: TestClient, seed_owners):
        phone = "+919876543210"
        # 1. Request OTP
        auth_client.post("/api/v1/auth/forgot-password", json={"phone_number": phone})
        otp = mock_sms_provider.get_last_otp(phone)

        # 2. Verify OTP
        verify_resp = auth_client.post(
            "/api/v1/auth/verify-otp",
            json={"phone_number": phone, "otp": otp},
        )
        reset_token = verify_resp.json()["reset_token"]

        # 3. Reset Password
        new_pwd = "BrandNewPassword2026!"
        reset_resp = auth_client.post(
            "/api/v1/auth/reset-password",
            json={
                "reset_token": reset_token,
                "new_password": new_pwd,
                "confirm_password": new_pwd,
            },
        )
        assert reset_resp.status_code == 200

        # 4. Old password must be rejected
        old_login = auth_client.post(
            "/api/v1/auth/login",
            json={"phone_number": phone, "password": "OwnerPassword123!"},
        )
        assert old_login.status_code == 401

        # 5. New password succeeds
        new_login = auth_client.post(
            "/api/v1/auth/login",
            json={"phone_number": phone, "password": new_pwd},
        )
        assert new_login.status_code == 200

    def test_password_reset_token_single_use(self, auth_client: TestClient, seed_owners):
        phone = "+919876543210"
        auth_client.post("/api/v1/auth/forgot-password", json={"phone_number": phone})
        otp = mock_sms_provider.get_last_otp(phone)
        verify_resp = auth_client.post(
            "/api/v1/auth/verify-otp",
            json={"phone_number": phone, "otp": otp},
        )
        reset_token = verify_resp.json()["reset_token"]

        # First use succeeds
        new_pwd = "StrongPassword789!"
        auth_client.post(
            "/api/v1/auth/reset-password",
            json={
                "reset_token": reset_token,
                "new_password": new_pwd,
                "confirm_password": new_pwd,
            },
        )

        # Second use must fail
        replay_resp = auth_client.post(
            "/api/v1/auth/reset-password",
            json={
                "reset_token": reset_token,
                "new_password": "AnotherPassword999!",
                "confirm_password": "AnotherPassword999!",
            },
        )
        assert replay_resp.status_code == 400
        assert "already been used" in replay_resp.json()["error"]["message"].lower()

    def test_weak_password_rejected_on_reset(self, auth_client: TestClient, seed_owners):
        phone = "+919876543210"
        auth_client.post("/api/v1/auth/forgot-password", json={"phone_number": phone})
        otp = mock_sms_provider.get_last_otp(phone)
        verify_resp = auth_client.post(
            "/api/v1/auth/verify-otp",
            json={"phone_number": phone, "otp": otp},
        )
        reset_token = verify_resp.json()["reset_token"]

        # Password without uppercase — rejected by service-layer strength check (400)
        # (Pydantic min_length=8 catches too-short passwords at schema level as 422)
        resp = auth_client.post(
            "/api/v1/auth/reset-password",
            json={
                "reset_token": reset_token,
                "new_password": "alllower1!",
                "confirm_password": "alllower1!",
            },
        )
        assert resp.status_code == 400
        assert "uppercase" in resp.json()["error"]["message"].lower()


# ---------------------------------------------------------------------------
# 6. Equal Owner Permissions & Audit Ledger Integrity
# ---------------------------------------------------------------------------


class TestOwnerPermissionsAndAuditing:
    def test_both_owners_have_equal_access(self, auth_client: TestClient, seed_owners):
        """Verify Owner 1 and Owner 2 can both authenticate and access identical routes."""
        # Owner 1
        login1 = auth_client.post(
            "/api/v1/auth/login",
            json={"phone_number": "+919876543210", "password": "OwnerPassword123!"},
        )
        assert login1.status_code == 200
        t1 = login1.json()["access_token"]
        me1 = auth_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {t1}"})
        assert me1.status_code == 200
        assert me1.json()["name"] == "Owner One"

        # Owner 2
        login2 = auth_client.post(
            "/api/v1/auth/login",
            json={"phone_number": "+919876543211", "password": "OwnerPassword456!"},
        )
        assert login2.status_code == 200
        t2 = login2.json()["access_token"]
        me2 = auth_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {t2}"})
        assert me2.status_code == 200
        assert me2.json()["name"] == "Owner Two"

    def test_audit_logs_contain_no_sensitive_secrets(
        self, auth_client: TestClient, seed_owners, test_db: Session
    ):
        """Inspect audit entries to ensure passwords, OTPs, and tokens are never logged."""
        phone = "+919876543210"
        auth_client.post(
            "/api/v1/auth/login",
            json={"phone_number": phone, "password": "OwnerPassword123!"},
        )
        auth_client.post("/api/v1/auth/forgot-password", json={"phone_number": phone})

        audit_entries = test_db.execute(select(AuditLog)).scalars().all()
        assert len(audit_entries) >= 2

        for entry in audit_entries:
            # Check previous_values and new_values payloads
            for payload in (entry.previous_values, entry.new_values):
                if payload:
                    for key, val in payload.items():
                        assert key.lower() not in (
                            "password",
                            "raw_password",
                            "otp",
                            "token",
                            "access_token",
                        )
                        if isinstance(val, str):
                            assert val != "OwnerPassword123!"
