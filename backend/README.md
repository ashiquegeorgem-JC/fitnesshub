# Regal Fitness — Backend Core

This directory contains the core backend services, database configuration, authentication system, and API application for **Regal Fitness**, a commercial gym management platform.

Developed by **Developer 2** on branch `developer-2-core`.

---

## Technical Stack

| Component | Technology |
|---|---|
| Language | Python 3.11+ |
| Web Framework | FastAPI (v0.115+) |
| ASGI Server | Uvicorn (v0.32+) |
| ORM | SQLAlchemy 2.0 |
| Validation | Pydantic v2 / Pydantic Settings |
| Database | PostgreSQL 14+ (psycopg2-binary driver) |
| Migrations | Alembic |
| Password Hashing | Argon2id (`argon2-cffi` v23.1+) |
| Authentication | JWT (`PyJWT` v2.8+) + Sliding Window Sessions |
| Testing | Pytest + HTTPX |

---

## Directory Structure

```
backend/
├── alembic/                    # Alembic migration scripts and environment
│   ├── versions/               # Migration version files
│   │   └── 001_initial_schema.py   # Initial full schema migration (21 tables)
│   └── env.py                  # Connects Alembic to app settings + Base metadata
├── alembic.ini                 # Alembic configuration
├── app/
│   ├── __init__.py             # App package version
│   ├── main.py                 # FastAPI entry point, lifespan, CORS, root routes
│   ├── api/                    # API routing architecture
│   │   ├── __init__.py
│   │   ├── deps.py             # Auth dependencies (get_current_owner, get_current_session)
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── api.py          # API router aggregator (api_router)
│   │       └── endpoints/
│   │           ├── __init__.py
│   │           ├── auth.py     # /api/v1/auth/* endpoints (login, refresh, sessions, OTP)
│   │           └── health.py   # /api/v1/health endpoints (live, ready, status)
│   ├── core/                   # Cross-cutting configuration and infrastructure
│   │   ├── __init__.py         # Exports: settings, logger, exceptions
│   │   ├── config.py           # Pydantic Settings — environment variables & validation
│   │   ├── exceptions.py       # Custom exception hierarchy (AppException + subclasses)
│   │   ├── handlers.py         # Centralized exception handler registration
│   │   ├── logging.py          # setup_logging(), structured log format, regal_fitness logger
│   │   ├── rate_limit.py       # Thread-safe sliding-window rate limiter
│   │   └── security.py         # Argon2id hashing, HMAC-SHA256 OTP, JWT issuance & decoding
│   ├── database/               # Database engine and session management
│   │   ├── __init__.py
│   │   ├── base.py             # SQLAlchemy DeclarativeBase
│   │   └── session.py          # Engine, SessionLocal, get_db dependency, check_db_connectivity()
│   ├── models/                 # SQLAlchemy ORM models (21 tables across 13 domain files)
│   │   ├── __init__.py         # Central export of all 21 models
│   │   ├── audit.py            # AuditLog
│   │   ├── gallery.py          # GalleryImage
│   │   ├── invoice.py          # Invoice
│   │   ├── member.py           # Member
│   │   ├── membership.py       # MembershipRecord, MembershipDueSchedule
│   │   ├── notification.py     # Notification
│   │   ├── owner.py            # Owner, OwnerNotificationPreference, OwnerDevicePushSubscription,
│   │   │                       # OwnerPasswordResetOTP, OwnerSession
│   │   ├── payment.py          # Payment, PaymentRefund
│   │   ├── plan.py             # MembershipPlan
│   │   ├── public.py           # JoiningApplication, GeneralEnquiry, GymVisitRequest
│   │   ├── sequence.py         # SystemSequence + 4 PostgreSQL Sequence objects
│   │   ├── setting.py          # SystemSetting
│   │   └── whatsapp.py         # WhatsAppMessageLog
│   ├── schemas/                # Pydantic schemas for request/response validation
│   │   ├── __init__.py
│   │   ├── auth.py             # Login, Token, Session, OTP, and Password Reset schemas
│   │   └── health.py           # RootResponse, HealthResponse
│   ├── services/               # Business logic and domain service operations
│   │   ├── __init__.py
│   │   ├── audit.py            # Sanitized audit logging service
│   │   ├── auth.py             # Core authentication, token rotation, sessions & OTP recovery
│   │   └── sms/                # SMS provider abstraction
│   │       ├── __init__.py     # Provider factory (get_sms_provider)
│   │       ├── base.py         # BaseSMSProvider abstract interface
│   │       ├── console.py      # Console logging SMS provider
│   │       ├── mock.py         # In-memory mock SMS provider for testing
│   │       └── twilio.py       # Twilio SMS provider integration
│   └── utils/                  # Common helper utilities and formatters
├── tests/                      # Pytest test suite
│   ├── __init__.py
│   ├── conftest.py             # Shared test client and database fixtures
│   ├── test_auth.py            # Phase 2 — Auth, token, session, OTP & security tests (28 tests)
│   ├── test_business_invariants.py  # Business rule invariant tests (9 tests)
│   ├── test_health.py          # Health check tests (5 tests)
│   ├── test_models.py          # ORM model tests (3 tests)
│   └── test_phase1_foundation.py    # Phase 1 foundation tests (75 tests)
├── requirements.txt            # Application dependencies
├── .env.example                # Environment variable template
└── README.md                   # This file
```

---

## Phase Completion Status

| Phase | Description | Status |
|---|---|---|
| 0.1 | Backend initialization, FastAPI skeleton | ✅ Approved & committed |
| 0.2 | Database schema design (`docs/DATABASE_SCHEMA.md`) | ✅ Approved |
| 0.3 | SQLAlchemy ORM models + Alembic migration | ✅ Approved |
| 1 | Backend foundation & configuration | ✅ Approved |
| 2 | Authentication & Owner Security (Argon2id, JWT, OTP, Sessions) | ✅ Complete — awaiting approval |
| 3 | Member management APIs | 🔜 Next phase |
| 4 | Membership & payment workflows | 🔜 Scheduled |

---

## Phase 2: Authentication & Owner Security Architecture

### 1. Dual-Owner Identity Model
- Regal Fitness is managed by exactly **two gym owners** with separate credentials and identical root-level permissions.
- Owners log in using their **registered phone number** (E.164 or 10-digit format) and **password**.
- Protected endpoints resolve the authenticated owner through dependency injection (`get_current_owner`), verifying both active account status (`is_active=True`) and active session status.

### 2. Password Security (Argon2id)
- Passwords are securely hashed using **Argon2id** (`argon2-cffi`), modern and memory-hard against GPU/ASIC attacks.
- Strong password complexity policy: minimum 8 characters, at least one uppercase letter, one lowercase letter, one digit, and one special character.
- Plaintext passwords are never stored or logged anywhere in the application.

### 3. JWT Access Tokens & Refresh Rotation
- **Access Tokens:** Standard JWT signed with HMAC-SHA256 (`HS256`), containing claims `sub` (owner_id), `phone`, `session_id`, `type: "access"`, and a unique `jti` (JWT ID). Validity: 30 minutes.
- **Refresh Tokens:** Long-lived tokens (7 days) tied to the `owner_sessions` table via SHA-256 hash. Plaintext refresh tokens are never persisted in the database.
- **Rotation:** Every refresh operation invalidates the old refresh token and issues a new access/refresh token pair.
- **Replay / Reuse Detection:** If an already-rotated or revoked refresh token is presented, the system detects a potential breach, revokes all sessions belonging to that owner immediately, and records a security audit log event.

### 4. Session Tracking & Multi-Device Control
- Every successful login creates a dedicated record in `owner_sessions` tracking `device_info`, `ip_address`, `expires_at`, and `last_active_at`.
- Endpoints provide full device management:
  - `GET /api/v1/auth/sessions`: List active sessions with current session highlighted.
  - `POST /api/v1/auth/logout`: Revoke current session.
  - `POST /api/v1/auth/logout-all`: Revoke all sessions across all devices for the owner.
  - `DELETE /api/v1/auth/sessions/{id}`: Terminate a specific remote session.

### 5. Forgot Password SMS OTP Workflow
- **Numeric OTP:** Cryptographically secure 6-digit numeric code generated via `secrets.choice`.
- **HMAC Storage:** OTPs are stored in `owner_password_reset_otps` as an **HMAC-SHA256 hash** using the server secret `OTP_HMAC_SECRET`. Plaintext OTPs are never stored in the database.
- **Lifecycle & Security:**
  - 10-minute expiry window.
  - 60-second cooldown between requests to prevent SMS flooding.
  - Maximum 3 verification attempts per OTP; automatically invalidated once limit is exceeded.
  - Single-use: consumed immediately upon verification.
- **Enumeration Protection:** Requesting an OTP for an unknown or inactive phone number returns a generic success message (`"If this phone number is registered..."`) to prevent user enumeration attacks.
- **Reset Token:** Upon successful OTP verification, a short-lived (15 min) JWT `password_reset` token is issued. This token is verified, single-use, and all existing active sessions are terminated upon password reset.

### 6. SMS Provider Abstraction
- Modular design under `app/services/sms/` implementing `BaseSMSProvider`:
  - `MockSMSProvider`: In-memory capture for automated testing and inspection.
  - `ConsoleSMSProvider`: Safe logging for local development without external credentials.
  - `TwilioSMSProvider`: Production SMS gateway integration via Twilio REST API.
- Configurable via `SMS_PROVIDER` environment variable (`mock`, `console`, `twilio`).

### 7. Rate Limiting & Audit Logging
- **Rate Limiting:** Sliding-window in-memory rate limiter protecting login endpoints (5 attempts per 5 minutes per phone number) and OTP generation. Exceeding the threshold returns HTTP 429 (`RATE_LIMIT_EXCEEDED`).
- **Audit Logging:** Security-sensitive events (`OWNER_LOGIN_SUCCESS`, `OWNER_LOGIN_FAILED`, `OWNER_LOGOUT`, `PASSWORD_RESET_REQUESTED`, `PASSWORD_RESET_SUCCESS`, `TOKEN_REUSE_DETECTED`, etc.) are recorded in the immutable `audit_logs` table.
- **Sanitization:** All logged details are sanitized to guarantee that passwords, plaintext OTPs, and secret keys are never written to audit trails or application logs.

---

## Authentication Endpoints Reference

All authentication routes are prefixed with `/api/v1/auth`:

| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| `POST` | `/api/v1/auth/login` | Owner login with phone and password | No (Rate Limited) |
| `POST` | `/api/v1/auth/refresh` | Refresh token pair with automatic rotation | No |
| `GET` | `/api/v1/auth/me` | Fetch authenticated owner profile & permissions | Yes (Bearer) |
| `POST` | `/api/v1/auth/logout` | Revoke current session | Yes (Bearer) |
| `POST` | `/api/v1/auth/logout-all` | Revoke all active sessions for current owner | Yes (Bearer) |
| `GET` | `/api/v1/auth/sessions` | List active sessions for current owner | Yes (Bearer) |
| `DELETE` | `/api/v1/auth/sessions/{id}` | Terminate a specific session | Yes (Bearer) |
| `POST` | `/api/v1/auth/forgot-password` | Request password reset 6-digit SMS OTP | No (Rate Limited) |
| `POST` | `/api/v1/auth/verify-otp` | Verify SMS OTP and receive reset token | No |
| `POST` | `/api/v1/auth/reset-password` | Reset password using verified reset token | No |

---

## Running Tests

```bash
# From backend/ directory with venv active
pytest -v
```

Current test suite status: **169 tests across 6 test files** — all passing.

| File | Tests | Coverage |
|---|---|---|
| `test_health.py` | 5 | Health endpoints (Phase 0.1) |
| `test_models.py` | 3 | ORM schema creation and instantiation |
| `test_business_invariants.py` | 9 | Business rule invariants |
| `test_phase1_foundation.py` | 75 | Phase 1 — settings, logging, session, exceptions, handlers, liveness, readiness, honest health status, lifespan |
| `test_auth.py` | 28 | Phase 2 — Owner login, Argon2id, JWT validation, token rotation & reuse detection, sessions, OTP workflow, equal permissions & audit sanitization |
| `test_security_audit_corrections.py` | 49 | Security Audit Corrections — Concurrency row locks, OTP single-use, atomic attempt counters, trusted proxy IP resolution, production secret & SMS validation, HTTP-layer OTP rate limiting, full password complexity policy, cross-owner session isolation |

---

## Getting Started

### 1. Install Dependencies
```bash
# From backend/ directory with venv active
pip install -r requirements.txt
```

### 2. Configure Environment Variables
```bash
Copy-Item .env.example .env  # Windows
cp .env.example .env         # Linux/macOS
```
Ensure `JWT_SECRET_KEY` and `OTP_HMAC_SECRET` are set to cryptographically secure strings in production.

### 3. Run Development Server
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
API Documentation: `http://localhost:8000/docs`
