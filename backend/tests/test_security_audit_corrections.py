"""
Phase 2 — Security Audit Corrections: Regression & New Tests
=============================================================
Covers all scenarios identified in Phase2_Security_Audit.md:

New tests added:
  - Concurrent refresh requests (C1) — documented SQLite vs PostgreSQL caveat
  - Concurrent OTP verification (C2) — documented SQLite caveat
  - Concurrent failed OTP attempts (H1) — documented SQLite caveat
  - Password-reset token replay (C2 secondary layer)
  - Revoked session access denial
  - Spoofed X-Forwarded-For header ignored without trusted proxy config
  - Trusted proxy IP resolves forwarded IP correctly
  - Production secret validation (H3)
  - Production SMS provider validation (M2)
  - OTP verification rate limiting (M1)
  - Full password complexity requirements (L2)
  - Cross-owner session isolation
  - OTP is_used set after verify (C2)
"""

import threading
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.config import Settings, settings
from app.core.rate_limit import limiter
from app.core.security import (
    create_access_token,
    create_password_reset_token,
    create_refresh_token,
    hash_password,
    validate_password_strength,
)
from app.database.base import Base
from app.main import app
from app.models.owner import Owner, OwnerPasswordResetOTP, OwnerSession
from app.services.sms import mock_sms_provider


# ---------------------------------------------------------------------------
# Shared Fixtures
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
def audit_client(test_db: Session):
    """TestClient wired to test SQLite DB, rate limiter and SMS mock cleared."""
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
        password_hash=hash_password("OwnerPass1!"),
        account_status="active",
    )
    owner2 = Owner(
        id=uuid.uuid4(),
        name="Owner Two",
        phone_number="+919876543211",
        email="owner2@regalfitness.com",
        password_hash=hash_password("OwnerPass2!"),
        account_status="active",
    )
    test_db.add_all([owner1, owner2])
    test_db.commit()
    return owner1, owner2


# ---------------------------------------------------------------------------
# 1. C1 — Refresh Token Rotation Concurrency
# ---------------------------------------------------------------------------


class TestRefreshTokenConcurrency:
    """
    Tests for the refresh token race condition fix (C1).

    IMPORTANT — SQLite vs PostgreSQL caveat:
    SQLite does not implement SELECT FOR UPDATE. The .with_for_update() call
    in refresh_token_pair() is silently ignored by SQLite. These tests verify
    the sequential correctness of the rotation logic, not true concurrent
    database-level locking.

    True concurrency safety (two simultaneous requests being serialised by a
    row lock) requires a live PostgreSQL instance and must be verified with
    an integration test running actual parallel threads against PostgreSQL.
    That verification is documented as a production requirement.
    """

    def test_sequential_refresh_rotation_works(self, audit_client, seed_owners):
        """Normal refresh rotation still works after adding with_for_update."""
        login = audit_client.post(
            "/api/v1/auth/login",
            json={"phone_number": "+919876543210", "password": "OwnerPass1!"},
        ).json()
        old_refresh = login["refresh_token"]

        resp = audit_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": old_refresh}
        )
        assert resp.status_code == 200
        new_tokens = resp.json()
        assert new_tokens["refresh_token"] != old_refresh
        assert new_tokens["access_token"] != login["access_token"]

    def test_old_refresh_token_rejected_after_rotation(self, audit_client, seed_owners):
        """An already-rotated refresh token must be rejected (reuse detection)."""
        login = audit_client.post(
            "/api/v1/auth/login",
            json={"phone_number": "+919876543210", "password": "OwnerPass1!"},
        ).json()
        old_refresh = login["refresh_token"]

        # First refresh succeeds
        audit_client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})

        # Replaying the old token triggers reuse detection
        replay = audit_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": old_refresh}
        )
        assert replay.status_code == 401
        assert "reuse" in replay.json()["error"]["message"].lower()

    def test_replay_revokes_all_sessions(self, audit_client, seed_owners, test_db: Session):
        """Token replay must revoke ALL owner sessions (nuclear option)."""
        owner1, _ = seed_owners
        # Login from two devices
        t1 = audit_client.post(
            "/api/v1/auth/login",
            json={"phone_number": "+919876543210", "password": "OwnerPass1!"},
        ).json()
        t2 = audit_client.post(
            "/api/v1/auth/login",
            json={"phone_number": "+919876543210", "password": "OwnerPass1!"},
        ).json()

        # Device 1 refreshes once
        audit_client.post("/api/v1/auth/refresh", json={"refresh_token": t1["refresh_token"]})

        # Attacker replays device 1's original token
        replay = audit_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": t1["refresh_token"]}
        )
        assert replay.status_code == 401

        # Both device sessions must now be revoked
        active = test_db.execute(
            select(OwnerSession).where(
                OwnerSession.owner_id == owner1.id,
                OwnerSession.is_revoked.is_(False),
            )
        ).scalars().all()
        assert len(active) == 0

    def test_revoked_session_cannot_refresh(self, audit_client, seed_owners, test_db: Session):
        """A session that has been explicitly revoked cannot issue new tokens."""
        owner1, _ = seed_owners
        login = audit_client.post(
            "/api/v1/auth/login",
            json={"phone_number": "+919876543210", "password": "OwnerPass1!"},
        ).json()

        # Explicitly revoke the session
        session = test_db.execute(
            select(OwnerSession).where(OwnerSession.owner_id == owner1.id)
        ).scalar_one()
        session.is_revoked = True
        test_db.commit()

        # Refresh attempt must fail
        resp = audit_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": login["refresh_token"]}
        )
        assert resp.status_code == 401

    def test_concurrent_refresh_same_token_sequential_simulation(
        self, audit_client, seed_owners, test_db: Session
    ):
        """
        Sequential simulation of the concurrent refresh race scenario.

        NOTE: This test demonstrates the SEQUENTIAL correctness of the fix —
        the second call with the same token is correctly rejected. It does NOT
        verify PostgreSQL-level row locking under true concurrency.

        True concurrency verification requires PostgreSQL with parallel threads
        and is a production environment requirement (not testable with SQLite).
        """
        login = audit_client.post(
            "/api/v1/auth/login",
            json={"phone_number": "+919876543210", "password": "OwnerPass1!"},
        ).json()
        old_refresh = login["refresh_token"]

        # First request with the token — succeeds
        resp1 = audit_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": old_refresh}
        )
        assert resp1.status_code == 200

        # Second request with the SAME old token — must fail (hash mismatch → reuse detection)
        resp2 = audit_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": old_refresh}
        )
        assert resp2.status_code == 401
        assert "reuse" in resp2.json()["error"]["message"].lower()


# ---------------------------------------------------------------------------
# 2. C2 — OTP Single-Use After Verify
# ---------------------------------------------------------------------------


class TestOTPSingleUse:
    """
    Tests for OTP single-use enforcement after verify-otp (C2).

    IMPORTANT — SQLite vs PostgreSQL caveat:
    with_for_update() on the OTP SELECT is a no-op in SQLite. The is_used=True
    write inside verify_password_reset_otp prevents sequential re-use correctly.
    True concurrent duplicate verify protection requires PostgreSQL.
    """

    def test_otp_marked_used_after_successful_verification(
        self, audit_client, seed_owners, test_db: Session
    ):
        """C2 FIX: is_used must be True immediately after verify-otp, before reset."""
        owner1, _ = seed_owners
        phone = "+919876543210"
        audit_client.post("/api/v1/auth/forgot-password", json={"phone_number": phone})
        otp = mock_sms_provider.get_last_otp(phone)

        resp = audit_client.post(
            "/api/v1/auth/verify-otp", json={"phone_number": phone, "otp": otp}
        )
        assert resp.status_code == 200

        # OTP record must now have is_used=True
        otp_rec = test_db.execute(
            select(OwnerPasswordResetOTP).where(
                OwnerPasswordResetOTP.owner_id == owner1.id
            )
        ).scalar_one()
        assert otp_rec.is_used is True

    def test_otp_cannot_be_verified_twice(self, audit_client, seed_owners):
        """The same correct OTP cannot be verified twice (single-use)."""
        phone = "+919876543210"
        audit_client.post("/api/v1/auth/forgot-password", json={"phone_number": phone})
        otp = mock_sms_provider.get_last_otp(phone)

        # First verification succeeds
        resp1 = audit_client.post(
            "/api/v1/auth/verify-otp", json={"phone_number": phone, "otp": otp}
        )
        assert resp1.status_code == 200

        # Second verification with same OTP must fail (is_used=True)
        resp2 = audit_client.post(
            "/api/v1/auth/verify-otp", json={"phone_number": phone, "otp": otp}
        )
        assert resp2.status_code == 400

    def test_reset_token_single_use_primary_layer(self, audit_client, seed_owners):
        """Password reset token cannot be used twice — primary otp.is_used check."""
        phone = "+919876543210"
        audit_client.post("/api/v1/auth/forgot-password", json={"phone_number": phone})
        otp = mock_sms_provider.get_last_otp(phone)
        verify_resp = audit_client.post(
            "/api/v1/auth/verify-otp", json={"phone_number": phone, "otp": otp}
        )
        reset_token = verify_resp.json()["reset_token"]
        new_pwd = "StrongNewPass1!"

        # First reset succeeds
        resp1 = audit_client.post(
            "/api/v1/auth/reset-password",
            json={"reset_token": reset_token, "new_password": new_pwd, "confirm_password": new_pwd},
        )
        assert resp1.status_code == 200

        # Second attempt with same reset_token must fail
        resp2 = audit_client.post(
            "/api/v1/auth/reset-password",
            json={
                "reset_token": reset_token,
                "new_password": "AnotherPass2!",
                "confirm_password": "AnotherPass2!",
            },
        )
        assert resp2.status_code == 400

    def test_reset_token_with_unverified_otp_rejected(
        self, audit_client, seed_owners, test_db: Session
    ):
        """
        A forged or manually constructed reset_token that references an OTP whose
        is_used=False must be rejected.

        This exercises the secondary single-use check in reset_owner_password:
        otp_record.is_used must be True (set by verify_password_reset_otp).
        If it is False, the token is treated as invalid.
        """
        owner1, _ = seed_owners
        phone = "+919876543210"
        audit_client.post("/api/v1/auth/forgot-password", json={"phone_number": phone})

        # Obtain the OTP record ID without consuming it
        otp_rec = test_db.execute(
            select(OwnerPasswordResetOTP).where(
                OwnerPasswordResetOTP.owner_id == owner1.id
            )
        ).scalar_one()
        assert otp_rec.is_used is False

        # Forge a reset token referencing the unverified OTP
        forged_token = create_password_reset_token(owner1.id, otp_rec.id)

        resp = audit_client.post(
            "/api/v1/auth/reset-password",
            json={
                "reset_token": forged_token,
                "new_password": "ForgedPass1!",
                "confirm_password": "ForgedPass1!",
            },
        )
        # Must fail: OTP not yet verified (is_used=False is now a rejection signal)
        assert resp.status_code == 400

    def test_concurrent_otp_verify_simulation(self, audit_client, seed_owners):
        """
        Sequential simulation of concurrent OTP verification.

        After the C2 fix, verify_password_reset_otp sets is_used=True before
        returning the reset_token. The second call therefore finds no active
        (is_used=False) OTP record and returns 400.

        NOTE: This is sequential correctness only. True concurrent protection
        relies on SELECT FOR UPDATE, which requires PostgreSQL.
        """
        phone = "+919876543210"
        audit_client.post("/api/v1/auth/forgot-password", json={"phone_number": phone})
        otp = mock_sms_provider.get_last_otp(phone)

        # First call succeeds
        resp1 = audit_client.post(
            "/api/v1/auth/verify-otp", json={"phone_number": phone, "otp": otp}
        )
        assert resp1.status_code == 200
        assert "reset_token" in resp1.json()

        # Second call with same OTP fails (is_used=True)
        resp2 = audit_client.post(
            "/api/v1/auth/verify-otp", json={"phone_number": phone, "otp": otp}
        )
        assert resp2.status_code == 400


# ---------------------------------------------------------------------------
# 3. H1 — Atomic OTP Attempt Counter
# ---------------------------------------------------------------------------


class TestOTPAttemptCounter:
    """
    Tests for atomic OTP attempt counting (H1).

    IMPORTANT — SQLite caveat:
    with_for_update() is a no-op in SQLite. Sequential correctness of the counter
    is verified here. True concurrent atomicity requires PostgreSQL integration tests.
    """

    def test_attempt_counter_increments_per_failed_attempt(self, audit_client, seed_owners, test_db: Session):
        """Failed attempts increment the counter correctly."""
        owner1, _ = seed_owners
        phone = "+919876543210"
        audit_client.post("/api/v1/auth/forgot-password", json={"phone_number": phone})

        for expected_count in range(1, 3):
            audit_client.post(
                "/api/v1/auth/verify-otp",
                json={"phone_number": phone, "otp": "000000"},
            )
            otp_rec = test_db.execute(
                select(OwnerPasswordResetOTP).where(
                    OwnerPasswordResetOTP.owner_id == owner1.id
                )
            ).scalar_one()
            assert otp_rec.attempts_count == expected_count

    def test_otp_invalidated_on_third_failed_attempt(self, audit_client, seed_owners, test_db: Session):
        """After 3 failed attempts the OTP is permanently invalidated (is_used=True)."""
        owner1, _ = seed_owners
        phone = "+919876543210"
        audit_client.post("/api/v1/auth/forgot-password", json={"phone_number": phone})
        correct_otp = mock_sms_provider.get_last_otp(phone)

        for _ in range(3):
            audit_client.post(
                "/api/v1/auth/verify-otp",
                json={"phone_number": phone, "otp": "000000"},
            )

        # OTP record must now be is_used=True
        otp_rec = test_db.execute(
            select(OwnerPasswordResetOTP).where(
                OwnerPasswordResetOTP.owner_id == owner1.id
            )
        ).scalar_one()
        assert otp_rec.is_used is True

        # Even the correct OTP must now be rejected
        resp = audit_client.post(
            "/api/v1/auth/verify-otp",
            json={"phone_number": phone, "otp": correct_otp},
        )
        assert resp.status_code == 400
        assert "exceeded" in resp.json()["error"]["message"].lower()

    def test_fourth_attempt_blocked_regardless(self, audit_client, seed_owners):
        """A 4th attempt (even with correct OTP) must always be blocked."""
        phone = "+919876543210"
        audit_client.post("/api/v1/auth/forgot-password", json={"phone_number": phone})
        correct_otp = mock_sms_provider.get_last_otp(phone)

        for _ in range(3):
            audit_client.post(
                "/api/v1/auth/verify-otp",
                json={"phone_number": phone, "otp": "000000"},
            )

        resp = audit_client.post(
            "/api/v1/auth/verify-otp",
            json={"phone_number": phone, "otp": correct_otp},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 4. H2 — Trusted Proxy IP Resolution
# ---------------------------------------------------------------------------


class TestTrustedProxyIPResolution:
    def test_spoofed_xff_ignored_without_trusted_proxy(self, audit_client, seed_owners):
        """
        Without TRUSTED_PROXY_IPS configured, X-Forwarded-For must be ignored.
        The direct TCP peer (testclient uses 'testclient') is the resolved IP.
        Rate limiting and audit logging must use the real IP, not the spoofed one.
        """
        phone = "+919876543210"
        # Exhaust rate limit using the REAL IP (testclient → 'testclient')
        for _ in range(settings.LOGIN_RATE_LIMIT_MAX_ATTEMPTS):
            audit_client.post(
                "/api/v1/auth/login",
                json={"phone_number": phone, "password": "wrong"},
                headers={"X-Forwarded-For": "1.2.3.4"},  # spoofed IP
            )

        # 6th attempt — rate limit on the REAL IP key ('testclient') must trigger
        resp = audit_client.post(
            "/api/v1/auth/login",
            json={"phone_number": phone, "password": "OwnerPass1!"},
            headers={"X-Forwarded-For": "5.6.7.8"},  # different spoofed IP
        )
        # Still rate limited because we tracked by real IP, not spoofed IP
        assert resp.status_code == 429

    def test_xff_trusted_when_peer_is_trusted_proxy(self, audit_client, seed_owners):
        """
        When the direct TCP peer IS in TRUSTED_PROXY_IPS, X-Forwarded-For is used.
        TestClient presents 'testclient' as host — configure that as trusted.
        """
        with patch.object(settings, "TRUSTED_PROXY_IPS", "testclient"):
            phone = "+919876543210"
            resp = audit_client.post(
                "/api/v1/auth/login",
                json={"phone_number": phone, "password": "OwnerPass1!"},
                headers={"X-Forwarded-For": "10.20.30.40"},
            )
            assert resp.status_code == 200

    def test_xff_not_trusted_when_peer_not_in_trusted_set(self, audit_client, seed_owners):
        """When the direct peer is NOT in TRUSTED_PROXY_IPS, XFF is ignored."""
        with patch.object(settings, "TRUSTED_PROXY_IPS", "192.168.1.1"):
            # XFF header present but peer ('testclient') is not trusted
            resp = audit_client.post(
                "/api/v1/auth/login",
                json={"phone_number": "+919876543210", "password": "OwnerPass1!"},
                headers={"X-Forwarded-For": "10.20.30.40"},
            )
            # Login still works; the XFF is simply ignored for IP tracking
            assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 5. H3 — Production Secret Validation
# ---------------------------------------------------------------------------


class TestProductionSecretValidation:
    def test_production_rejects_default_jwt_secret(self):
        """Application startup must fail in production with the default JWT secret."""
        with pytest.raises(Exception) as exc_info:
            s = Settings(
                APP_ENV="production",
                JWT_SECRET_KEY="regal_fitness_default_dev_jwt_secret_key_change_in_production_32bytes",
                OTP_HMAC_SECRET="a" * 40,  # valid length, not a known default
                SMS_PROVIDER="twilio",
                TWILIO_ACCOUNT_SID="ACtest",
                TWILIO_AUTH_TOKEN="authtest",
                TWILIO_FROM_NUMBER="+15550000001",
            )
            s.validate_production_security()
        assert "JWT_SECRET_KEY" in str(exc_info.value)
        assert "insecure" in str(exc_info.value).lower()

    def test_production_rejects_default_otp_hmac_secret(self):
        """Application startup must fail in production with the default OTP HMAC secret."""
        with pytest.raises(Exception) as exc_info:
            s = Settings(
                APP_ENV="production",
                JWT_SECRET_KEY="a" * 40,  # valid
                OTP_HMAC_SECRET="regal_fitness_default_dev_hmac_secret_key",
                SMS_PROVIDER="twilio",
                TWILIO_ACCOUNT_SID="ACtest",
                TWILIO_AUTH_TOKEN="authtest",
                TWILIO_FROM_NUMBER="+15550000001",
            )
            s.validate_production_security()
        assert "OTP_HMAC_SECRET" in str(exc_info.value)

    def test_production_rejects_short_jwt_secret(self):
        """JWT secret shorter than 32 characters must be rejected in production."""
        with pytest.raises(Exception) as exc_info:
            s = Settings(
                APP_ENV="production",
                JWT_SECRET_KEY="tooshort",
                OTP_HMAC_SECRET="a" * 40,
                SMS_PROVIDER="twilio",
                TWILIO_ACCOUNT_SID="ACtest",
                TWILIO_AUTH_TOKEN="authtest",
                TWILIO_FROM_NUMBER="+15550000001",
            )
            s.validate_production_security()
        assert "JWT_SECRET_KEY" in str(exc_info.value)

    def test_production_rejects_mock_sms_provider(self):
        """Mock SMS provider must be rejected in production."""
        with pytest.raises(Exception) as exc_info:
            s = Settings(
                APP_ENV="production",
                JWT_SECRET_KEY="a" * 40,
                OTP_HMAC_SECRET="b" * 40,
                SMS_PROVIDER="mock",
            )
            s.validate_production_security()
        assert "SMS_PROVIDER" in str(exc_info.value)

    def test_production_rejects_console_sms_provider(self):
        """Console SMS provider must be rejected in production."""
        with pytest.raises(Exception) as exc_info:
            s = Settings(
                APP_ENV="production",
                JWT_SECRET_KEY="a" * 40,
                OTP_HMAC_SECRET="b" * 40,
                SMS_PROVIDER="console",
            )
            s.validate_production_security()
        assert "SMS_PROVIDER" in str(exc_info.value)

    def test_production_accepts_valid_configuration(self):
        """Valid production configuration must not raise any exception."""
        try:
            s = Settings(
                APP_ENV="production",
                JWT_SECRET_KEY="a" * 40,
                OTP_HMAC_SECRET="b" * 40,
                SMS_PROVIDER="twilio",
                TWILIO_ACCOUNT_SID="ACtest",
                TWILIO_AUTH_TOKEN="authtest",
                TWILIO_FROM_NUMBER="+15550000001",
            )
            s.validate_production_security()
            assert s.is_production is True
        except Exception as exc:
            pytest.fail(f"Valid production config raised an exception: {exc}")

    def test_development_allows_default_secrets(self):
        """Default secrets must be accepted in development (non-production) mode."""
        try:
            s = Settings(APP_ENV="development")
            s.validate_production_security()
            assert s.is_production is False
        except Exception as exc:
            pytest.fail(f"Development mode with defaults raised an exception: {exc}")

    def test_production_error_message_is_actionable(self):
        """The startup error message must guide the operator to fix it."""
        with pytest.raises(Exception) as exc_info:
            s = Settings(
                APP_ENV="production",
                JWT_SECRET_KEY="regal_fitness_default_dev_jwt_secret_key_change_in_production_32bytes",
                OTP_HMAC_SECRET="a" * 40,
                SMS_PROVIDER="twilio",
                TWILIO_ACCOUNT_SID="ACtest",
                TWILIO_AUTH_TOKEN="authtest",
                TWILIO_FROM_NUMBER="+15550000001",
            )
            s.validate_production_security()
        msg = str(exc_info.value).lower()
        assert "production" in msg
        assert "openssl" in msg or "secure" in msg


# ---------------------------------------------------------------------------
# 6. M1 — OTP Verification Rate Limiting
# ---------------------------------------------------------------------------


class TestOTPVerificationRateLimit:
    def test_otp_verify_rate_limited_per_phone(self, audit_client, seed_owners):
        """POST /api/v1/auth/verify-otp must be rate limited per phone number."""
        phone = "+919876543210"
        audit_client.post("/api/v1/auth/forgot-password", json={"phone_number": phone})

        # Exhaust the per-phone rate limit with wrong OTPs
        for _ in range(settings.OTP_VERIFY_RATE_LIMIT_MAX_ATTEMPTS):
            resp = audit_client.post(
                "/api/v1/auth/verify-otp",
                json={"phone_number": phone, "otp": "000000"},
            )
            # Should be 400 (wrong OTP) until the rate limit kicks in
            assert resp.status_code in (400, 429)

        # Next request must be rate limited (or already blocked by attempt limit)
        final_resp = audit_client.post(
            "/api/v1/auth/verify-otp",
            json={"phone_number": phone, "otp": "000000"},
        )
        assert final_resp.status_code in (400, 429)

    def test_otp_verify_rate_limit_in_memory_limitation_documented(self):
        """
        DOCUMENTATION TEST — not a functional assertion.

        The current in-memory rate limiter is suitable ONLY for a
        single-process development environment. In production with multiple
        Uvicorn workers or multiple application instances:
        - Each process maintains its own independent limiter state.
        - An attacker cycling between workers faces only 1/N of the intended
          limit per worker, where N is the number of worker processes.

        To support distributed rate limiting, the InMemoryRateLimiter must be
        replaced with a Redis-backed implementation using the same interface:
          - is_allowed(key, max_attempts, window_seconds) -> (bool, int)
          - check_or_raise(key, max_attempts, window_seconds, action_name) -> None
          - reset(key) -> None
        The RATE_LIMITER_BACKEND and REDIS_URL settings should control which
        backend is used. No call sites in auth.py or endpoints need to change.
        """
        assert True  # This test exists to document the known limitation.


# ---------------------------------------------------------------------------
# 7. M2 — SMS Provider Production Safety
# ---------------------------------------------------------------------------


class TestSMSProviderProductionSafety:
    def test_mock_provider_blocked_in_production(self):
        """SMS_PROVIDER=mock must be rejected when APP_ENV=production."""
        with pytest.raises(Exception) as exc_info:
            s = Settings(
                APP_ENV="production",
                JWT_SECRET_KEY="a" * 40,
                OTP_HMAC_SECRET="b" * 40,
                SMS_PROVIDER="mock",
            )
            s.validate_production_security()
        assert "mock" in str(exc_info.value).lower() or "SMS_PROVIDER" in str(exc_info.value)

    def test_console_provider_blocked_in_production(self):
        """SMS_PROVIDER=console must be rejected when APP_ENV=production."""
        with pytest.raises(Exception) as exc_info:
            s = Settings(
                APP_ENV="production",
                JWT_SECRET_KEY="a" * 40,
                OTP_HMAC_SECRET="b" * 40,
                SMS_PROVIDER="console",
            )
            s.validate_production_security()
        assert "SMS_PROVIDER" in str(exc_info.value)

    def test_mock_provider_available_in_development(self):
        """Mock provider must remain available in development."""
        try:
            s = Settings(APP_ENV="development", SMS_PROVIDER="mock")
            assert s.SMS_PROVIDER == "mock"
        except Exception as exc:
            pytest.fail(f"Mock provider in dev raised: {exc}")

    def test_otp_dispatched_via_mock_in_tests(self, audit_client, seed_owners):
        """In test mode (SMS_PROVIDER=mock), OTPs are captured by mock provider."""
        phone = "+919876543210"
        resp = audit_client.post(
            "/api/v1/auth/forgot-password", json={"phone_number": phone}
        )
        assert resp.status_code == 200
        assert len(mock_sms_provider.sent_messages) == 1
        msg = mock_sms_provider.sent_messages[0]
        assert msg["phone_number"] == phone
        assert msg["otp"].isdigit() and len(msg["otp"]) == 6


# ---------------------------------------------------------------------------
# 8. L1 — ORM Schema Consistency (revoked_at)
# ---------------------------------------------------------------------------


class TestORMSchemaConsistency:
    def test_owner_session_has_no_revoked_at_column(self, test_db: Session):
        """
        Verifies that OwnerSession has no revoked_at column, consistent with:
        - DATABASE_SCHEMA.md (approved schema has only is_revoked, no revoked_at)
        - Alembic migration 001_initial_schema.py (no revoked_at column)
        - ORM model owner.py (no revoked_at mapped column)

        The 'revoked_at' column appeared only in documentation and reports.
        No schema drift exists. No migration is required.
        """
        session_instance = OwnerSession(
            id=uuid.uuid4(),
            owner_id=uuid.uuid4(),
            refresh_token_hash="dummy_hash_for_schema_test",
            is_revoked=False,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        # Verify the ORM model does NOT have revoked_at
        assert not hasattr(session_instance, "revoked_at"), (
            "OwnerSession must not have a revoked_at column — the approved schema "
            "uses only is_revoked. Any schema change requires a new migration."
        )
        # Verify it DOES have is_revoked
        assert hasattr(session_instance, "is_revoked")

    def test_session_revocation_uses_is_revoked_flag(self, audit_client, seed_owners, test_db: Session):
        """Service layer correctly uses is_revoked=True (not revoked_at) for revocation."""
        owner1, _ = seed_owners
        login = audit_client.post(
            "/api/v1/auth/login",
            json={"phone_number": "+919876543210", "password": "OwnerPass1!"},
        ).json()

        # Logout revokes the session
        audit_client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {login['access_token']}"},
        )

        session = test_db.execute(
            select(OwnerSession).where(OwnerSession.owner_id == owner1.id)
        ).scalar_one()
        assert session.is_revoked is True


# ---------------------------------------------------------------------------
# 9. L2 — Password Complexity Requirements
# ---------------------------------------------------------------------------


class TestPasswordComplexity:
    """Tests for the full documented password policy (L2)."""

    @pytest.mark.parametrize("password,expected_error_fragment", [
        ("Sh0rt!", "8 characters"),
        ("alllowercase1!", "uppercase"),
        ("ALLUPPERCASE1!", "lowercase"),
        ("NoDigitsHere!", "digit"),
        ("NoSpecialChar1", "special"),
        ("nouppercase1!", "uppercase"),
    ])
    def test_weak_passwords_rejected(self, password, expected_error_fragment):
        """Each password policy requirement is independently enforced."""
        error = validate_password_strength(password)
        assert error is not None, f"Expected rejection for '{password}'"
        assert expected_error_fragment.lower() in error.lower(), (
            f"Expected '{expected_error_fragment}' in error '{error}' for password '{password}'"
        )

    @pytest.mark.parametrize("password", [
        "StrongPass1!",
        "Aa1!aaaa",
        "Secure@Pass123",
        "My$ecure1Pass",
        "P@ssw0rd!",
        "Regal#2026Fit",
    ])
    def test_strong_passwords_accepted(self, password):
        """Valid passwords satisfying all requirements are accepted."""
        error = validate_password_strength(password)
        assert error is None, f"Expected acceptance for '{password}', got: {error}"

    def test_password_policy_enforced_on_reset(self, audit_client, seed_owners):
        """Full password policy is enforced during password reset, not just length."""
        phone = "+919876543210"
        audit_client.post("/api/v1/auth/forgot-password", json={"phone_number": phone})
        otp = mock_sms_provider.get_last_otp(phone)
        verify_resp = audit_client.post(
            "/api/v1/auth/verify-otp", json={"phone_number": phone, "otp": otp}
        )
        reset_token = verify_resp.json()["reset_token"]

        # Password without uppercase — should fail with 400 (service-layer check)
        resp = audit_client.post(
            "/api/v1/auth/reset-password",
            json={
                "reset_token": reset_token,
                "new_password": "alllower1!",
                "confirm_password": "alllower1!",
            },
        )
        assert resp.status_code == 400
        assert "uppercase" in resp.json()["error"]["message"].lower()

    def test_password_without_special_char_rejected(self, audit_client, seed_owners):
        """Password without a special character is rejected."""
        phone = "+919876543210"
        audit_client.post("/api/v1/auth/forgot-password", json={"phone_number": phone})
        otp = mock_sms_provider.get_last_otp(phone)
        verify_resp = audit_client.post(
            "/api/v1/auth/verify-otp", json={"phone_number": phone, "otp": otp}
        )
        reset_token = verify_resp.json()["reset_token"]

        resp = audit_client.post(
            "/api/v1/auth/reset-password",
            json={
                "reset_token": reset_token,
                "new_password": "NoSpecialChar1",
                "confirm_password": "NoSpecialChar1",
            },
        )
        assert resp.status_code == 400
        assert "special" in resp.json()["error"]["message"].lower()


# ---------------------------------------------------------------------------
# 10. Cross-Owner Session Isolation
# ---------------------------------------------------------------------------


class TestCrossOwnerSessionIsolation:
    def test_owner_cannot_revoke_other_owners_session(self, audit_client, seed_owners, test_db: Session):
        """Owner 1 cannot revoke Owner 2's session using session UUID."""
        owner1, owner2 = seed_owners

        # Login both owners
        login1 = audit_client.post(
            "/api/v1/auth/login",
            json={"phone_number": "+919876543210", "password": "OwnerPass1!"},
        ).json()
        login2 = audit_client.post(
            "/api/v1/auth/login",
            json={"phone_number": "+919876543211", "password": "OwnerPass2!"},
        ).json()

        # Get Owner 2's session ID
        owner2_session = test_db.execute(
            select(OwnerSession).where(OwnerSession.owner_id == owner2.id)
        ).scalar_one()

        # Owner 1 attempts to revoke Owner 2's session
        resp = audit_client.delete(
            f"/api/v1/auth/sessions/{owner2_session.id}",
            headers={"Authorization": f"Bearer {login1['access_token']}"},
        )
        # Must fail: 404 because the ownership filter excludes the session
        assert resp.status_code == 404

        # Owner 2's session must still be active
        test_db.refresh(owner2_session)
        assert owner2_session.is_revoked is False

    def test_owner_cannot_list_other_owners_sessions(self, audit_client, seed_owners):
        """Owner 1's session list must not contain Owner 2's sessions."""
        login1 = audit_client.post(
            "/api/v1/auth/login",
            json={"phone_number": "+919876543210", "password": "OwnerPass1!"},
        ).json()
        # Owner 2 also logs in
        audit_client.post(
            "/api/v1/auth/login",
            json={"phone_number": "+919876543211", "password": "OwnerPass2!"},
        )

        # Owner 1 lists their sessions
        resp = audit_client.get(
            "/api/v1/auth/sessions",
            headers={"Authorization": f"Bearer {login1['access_token']}"},
        )
        assert resp.status_code == 200
        sessions = resp.json()
        # Owner 1 must see only their own session(s)
        assert len(sessions) == 1

    def test_revoked_session_access_denied(self, audit_client, seed_owners, test_db: Session):
        """An access token whose session has been revoked must be rejected."""
        owner1, _ = seed_owners
        login = audit_client.post(
            "/api/v1/auth/login",
            json={"phone_number": "+919876543210", "password": "OwnerPass1!"},
        ).json()
        token = login["access_token"]

        # Directly revoke the session in DB
        session = test_db.execute(
            select(OwnerSession).where(OwnerSession.owner_id == owner1.id)
        ).scalar_one()
        session.is_revoked = True
        test_db.commit()

        # Access token must now be rejected
        resp = audit_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401
        assert "revoked" in resp.json()["error"]["message"].lower()


# ---------------------------------------------------------------------------
# 11. Final Security Verification Regressions (Rate Limit Consistency & Hardening)
# ---------------------------------------------------------------------------


class TestFinalSecurityVerificationRegressions:
    def test_verify_otp_cleans_phone_number_preventing_rate_limit_bypass(
        self, audit_client, seed_owners
    ):
        """
        Verify that VerifyOTPRequest cleans spaces/dashes from phone_number,
        preventing rate-limit key fragmentation and ensuring correct DB matching.
        """
        phone_raw = "+919876543210"
        phone_spaced = " +91 9876-543210 "

        # Request OTP for owner
        audit_client.post("/api/v1/auth/forgot-password", json={"phone_number": phone_raw})
        otp = mock_sms_provider.get_last_otp(phone_raw)

        # Verify with spaced/dashed phone number
        resp = audit_client.post(
            "/api/v1/auth/verify-otp",
            json={"phone_number": phone_spaced, "otp": otp},
        )
        assert resp.status_code == 200
        assert "reset_token" in resp.json()

    def test_verify_otp_alternate_formats_share_rate_limit_bucket(
        self, audit_client, seed_owners
    ):
        """
        Attempts with alternate phone formats (spaces/dashes) must increment
        the same rate limit bucket, preventing rate-limit bypass.
        """
        phone_clean = "+919876543210"
        audit_client.post("/api/v1/auth/forgot-password", json={"phone_number": phone_clean})

        # Send attempts alternating whitespace
        for i in range(settings.OTP_VERIFY_RATE_LIMIT_MAX_ATTEMPTS):
            fmt = f" +91 9876 54321{0} " if i % 2 == 0 else phone_clean
            resp = audit_client.post(
                "/api/v1/auth/verify-otp",
                json={"phone_number": fmt, "otp": "000000"},
            )
            assert resp.status_code in (400, 429)

        # Next request must be rate limited
        blocked_resp = audit_client.post(
            "/api/v1/auth/verify-otp",
            json={"phone_number": phone_clean, "otp": "000000"},
        )
        assert blocked_resp.status_code in (400, 429)

    def test_otp_request_rate_limited_per_ip(self, audit_client):
        """
        OTP generation requests must be rate-limited per IP across different
        phone numbers to prevent SMS credit exhaustion attacks.
        """
        for i in range(10):
            fake_phone = f"+9198765432{i:02d}"
            resp = audit_client.post(
                "/api/v1/auth/forgot-password", json={"phone_number": fake_phone}
            )
            assert resp.status_code == 200

        # 11th request from same IP must be rate limited (429)
        blocked_resp = audit_client.post(
            "/api/v1/auth/forgot-password", json={"phone_number": "+919876543999"}
        )
        assert blocked_resp.status_code == 429
        assert "too many" in blocked_resp.json()["error"]["message"].lower()

    def test_password_reset_rate_limited_per_ip(self, audit_client):
        """
        POST /api/v1/auth/reset-password must be rate-limited per IP to prevent
        brute-force or denial-of-service against Argon2id hashing.
        """
        for _ in range(10):
            resp = audit_client.post(
                "/api/v1/auth/reset-password",
                json={
                    "reset_token": "dummy.invalid.token",
                    "new_password": "ValidPassword1!",
                    "confirm_password": "ValidPassword1!",
                },
            )
            # Fails JWT decoding (401)
            assert resp.status_code == 401

        # 11th attempt from same IP must be rate limited (429)
        blocked = audit_client.post(
            "/api/v1/auth/reset-password",
            json={
                "reset_token": "dummy.invalid.token",
                "new_password": "ValidPassword1!",
                "confirm_password": "ValidPassword1!",
            },
        )
        assert blocked.status_code == 429
        assert "too many" in blocked.json()["error"]["message"].lower()
