"""
Phase 1 Foundation Tests — Regal Fitness Backend
=================================================
Verifies that all Phase 1 components are correctly configured:
  - Pydantic Settings and environment-based configuration
  - Structured logging setup
  - Database session and connectivity probe
  - Custom exception hierarchy
  - Centralized exception handlers (error response schema)
  - Health endpoints (root-level and /api/v1/health)
  - Application lifespan (startup without crash when DB is offline)
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch

# ---------------------------------------------------------------------------
# 1. Settings / Configuration
# ---------------------------------------------------------------------------


class TestSettings:
    """Verify Pydantic Settings loads correctly with defaults."""

    def test_app_name_default(self):
        from app.core.config import settings

        assert settings.APP_NAME == "Regal Fitness API"

    def test_app_version_exists(self):
        from app.core.config import settings

        assert settings.APP_VERSION and isinstance(settings.APP_VERSION, str)

    def test_api_prefix(self):
        from app.core.config import settings

        assert settings.API_V1_STR == "/api/v1"

    def test_log_level_default(self):
        from app.core.config import settings

        assert settings.LOG_LEVEL.upper() in (
            "DEBUG",
            "INFO",
            "WARNING",
            "ERROR",
            "CRITICAL",
        )

    def test_otp_hmac_secret_has_value(self):
        from app.core.config import settings

        assert settings.OTP_HMAC_SECRET and len(settings.OTP_HMAC_SECRET) >= 10

    def test_whatsapp_flag_is_bool(self):
        from app.core.config import settings

        assert isinstance(settings.WHATSAPP_AUTOMATION_ENABLED, bool)

    def test_cors_origins_is_list(self):
        from app.core.config import settings

        assert isinstance(settings.ALLOWED_CORS_ORIGINS, list)
        assert len(settings.ALLOWED_CORS_ORIGINS) >= 1

    def test_database_url_exists(self):
        from app.core.config import settings

        assert settings.DATABASE_URL and "postgresql" in settings.DATABASE_URL.lower()

    def test_is_production_property_false_in_dev(self):
        """is_production must be False when APP_ENV is 'development'."""
        from app.core.config import Settings

        s = Settings(APP_ENV="development")
        assert s.is_production is False

    def test_is_production_property_true_for_prod(self):
        from app.core.config import Settings

        s = Settings(APP_ENV="production")
        assert s.is_production is True

    def test_is_production_property_true_for_prod_alias(self):
        from app.core.config import Settings

        s = Settings(APP_ENV="prod")
        assert s.is_production is True

    def test_cors_validator_parses_comma_string(self):
        from app.core.config import Settings

        s = Settings(ALLOWED_CORS_ORIGINS="http://a.com,http://b.com")
        assert "http://a.com" in s.ALLOWED_CORS_ORIGINS
        assert "http://b.com" in s.ALLOWED_CORS_ORIGINS

    def test_cors_validator_parses_json_array_string(self):
        from app.core.config import Settings

        s = Settings(ALLOWED_CORS_ORIGINS='["http://a.com", "http://b.com"]')
        assert "http://a.com" in s.ALLOWED_CORS_ORIGINS


# ---------------------------------------------------------------------------
# 2. Logging
# ---------------------------------------------------------------------------


class TestLogging:
    """Verify setup_logging runs without error and logger is correctly named."""

    def test_setup_logging_runs_without_error(self):
        from app.core.logging import setup_logging

        setup_logging()  # Must not raise

    def test_logger_name_is_regal_fitness(self):
        from app.core.logging import logger

        assert logger.name == "regal_fitness"

    def test_logger_is_logging_logger(self):
        import logging
        from app.core.logging import logger

        assert isinstance(logger, logging.Logger)


# ---------------------------------------------------------------------------
# 3. Database Session / Connectivity
# ---------------------------------------------------------------------------


class TestDatabaseSession:
    """Verify check_db_connectivity returns a valid dict even when offline."""

    def test_check_db_connectivity_returns_dict(self):
        from app.database.session import check_db_connectivity

        result = check_db_connectivity()
        assert isinstance(result, dict)

    def test_check_db_connectivity_has_status_key(self):
        from app.database.session import check_db_connectivity

        result = check_db_connectivity()
        assert "status" in result

    def test_check_db_connectivity_status_is_string(self):
        from app.database.session import check_db_connectivity

        result = check_db_connectivity()
        assert isinstance(result["status"], str)

    def test_check_db_connectivity_status_known_value(self):
        """Status must be either 'connected' or 'disconnected'."""
        from app.database.session import check_db_connectivity

        result = check_db_connectivity()
        assert result["status"] in ("connected", "disconnected")

    def test_check_db_connectivity_has_dialect_key(self):
        from app.database.session import check_db_connectivity

        result = check_db_connectivity()
        assert "dialect" in result

    def test_check_db_connectivity_dialect_postgresql(self):
        from app.database.session import check_db_connectivity

        result = check_db_connectivity()
        assert result["dialect"] == "postgresql"

    def test_check_db_connectivity_no_exception_when_offline(self):
        """
        Even when the DB is unreachable, the function must return gracefully —
        never raise an exception to the caller.
        """
        from sqlalchemy.exc import OperationalError
        from app.database.session import check_db_connectivity, engine

        with patch.object(
            engine,
            "connect",
            side_effect=OperationalError("connect", {}, Exception("refused")),
        ):
            result = check_db_connectivity()
        assert result["status"] == "disconnected"

    def test_session_factory_exists(self):
        from app.database.session import SessionLocal

        assert SessionLocal is not None

    def test_get_db_yields_session(self):
        """get_db dependency must yield a session object (SQLite in-memory mock)."""
        from sqlalchemy import create_engine as _ce
        from sqlalchemy.orm import sessionmaker
        from unittest.mock import patch as _patch
        from app.database.session import get_db

        # Patch SessionLocal to use in-memory SQLite
        sqlite_engine = _ce("sqlite:///:memory:")
        MockSessionLocal = sessionmaker(bind=sqlite_engine)
        with _patch("app.database.session.SessionLocal", MockSessionLocal):
            gen = get_db()
            session = next(gen)
            assert session is not None
            # Clean up
            try:
                next(gen)
            except StopIteration:
                pass


# ---------------------------------------------------------------------------
# 4. Exception Hierarchy
# ---------------------------------------------------------------------------


class TestExceptions:
    """Verify custom exception classes have correct status codes and error codes."""

    def test_app_exception_defaults(self):
        from app.core.exceptions import AppException

        exc = AppException()
        assert exc.status_code == 500
        assert exc.error_code == "INTERNAL_SERVER_ERROR"

    def test_app_exception_custom_values(self):
        from app.core.exceptions import AppException

        exc = AppException(detail="test", status_code=418, error_code="TEAPOT")
        assert exc.status_code == 418
        assert exc.error_code == "TEAPOT"
        assert exc.detail == "test"

    def test_resource_not_found_exception(self):
        from app.core.exceptions import ResourceNotFoundException

        exc = ResourceNotFoundException(resource="Member", identifier="RF001")
        assert exc.status_code == 404
        assert exc.error_code == "RESOURCE_NOT_FOUND"
        assert "RF001" in exc.detail

    def test_resource_not_found_without_identifier(self):
        from app.core.exceptions import ResourceNotFoundException

        exc = ResourceNotFoundException(resource="Plan")
        assert exc.status_code == 404
        assert "Plan" in exc.detail

    def test_conflict_exception(self):
        from app.core.exceptions import ConflictException

        exc = ConflictException(detail="Phone already registered")
        assert exc.status_code == 409
        assert exc.error_code == "RESOURCE_CONFLICT"

    def test_bad_request_exception(self):
        from app.core.exceptions import BadRequestException

        exc = BadRequestException(detail="Missing required field")
        assert exc.status_code == 400
        assert exc.error_code == "BAD_REQUEST"

    def test_database_connection_exception(self):
        from app.core.exceptions import DatabaseConnectionException

        exc = DatabaseConnectionException()
        assert exc.status_code == 503
        assert exc.error_code == "DATABASE_UNAVAILABLE"

    def test_exceptions_are_subclasses_of_app_exception(self):
        from app.core.exceptions import (
            AppException,
            ResourceNotFoundException,
            ConflictException,
            BadRequestException,
            DatabaseConnectionException,
        )

        for cls in (
            ResourceNotFoundException,
            ConflictException,
            BadRequestException,
            DatabaseConnectionException,
        ):
            assert issubclass(cls, AppException)


# ---------------------------------------------------------------------------
# 5. Exception Handlers — Error Response Schema
# ---------------------------------------------------------------------------


class TestExceptionHandlers:
    """Verify handler registration and correct JSON error schema {"error": {...}}."""

    @pytest.fixture(scope="class")
    def test_app(self):
        """Minimal FastAPI app with exception handlers and a few test routes."""
        from fastapi import FastAPI
        from app.core.handlers import register_exception_handlers
        from app.core.exceptions import (
            ResourceNotFoundException,
            ConflictException,
            BadRequestException,
        )
        from fastapi import HTTPException
        from pydantic import BaseModel

        app = FastAPI()
        register_exception_handlers(app)

        class Item(BaseModel):
            name: str
            count: int

        @app.get("/test/not-found")
        def trigger_not_found():
            raise ResourceNotFoundException(resource="Member", identifier="RF001")

        @app.get("/test/conflict")
        def trigger_conflict():
            raise ConflictException(detail="Duplicate phone")

        @app.get("/test/bad-request")
        def trigger_bad_request():
            raise BadRequestException(detail="Invalid date format")

        @app.get("/test/http-exception")
        def trigger_http_exception():
            raise HTTPException(status_code=403, detail="Forbidden resource")

        @app.post("/test/validation")
        def trigger_validation(item: Item):
            return item

        @app.get("/test/unhandled")
        def trigger_unhandled():
            raise RuntimeError("Something went wrong")

        return TestClient(app, raise_server_exceptions=False)

    def _assert_error_schema(self, response):
        """Helper: assert response has {"error": {"code":..., "message":..., "details":...}}."""
        body = response.json()
        assert "error" in body, f"Expected 'error' key in response body: {body}"
        err = body["error"]
        assert "code" in err, f"Expected 'code' in error: {err}"
        assert "message" in err, f"Expected 'message' in error: {err}"
        assert "details" in err, f"Expected 'details' in error: {err}"

    def test_resource_not_found_returns_404(self, test_app):
        resp = test_app.get("/test/not-found")
        assert resp.status_code == 404
        self._assert_error_schema(resp)
        assert resp.json()["error"]["code"] == "RESOURCE_NOT_FOUND"

    def test_resource_not_found_message_contains_identifier(self, test_app):
        resp = test_app.get("/test/not-found")
        assert "RF001" in resp.json()["error"]["message"]

    def test_conflict_returns_409(self, test_app):
        resp = test_app.get("/test/conflict")
        assert resp.status_code == 409
        self._assert_error_schema(resp)
        assert resp.json()["error"]["code"] == "RESOURCE_CONFLICT"

    def test_bad_request_returns_400(self, test_app):
        resp = test_app.get("/test/bad-request")
        assert resp.status_code == 400
        self._assert_error_schema(resp)
        assert resp.json()["error"]["code"] == "BAD_REQUEST"

    def test_http_exception_handler(self, test_app):
        resp = test_app.get("/test/http-exception")
        assert resp.status_code == 403
        self._assert_error_schema(resp)
        assert resp.json()["error"]["code"] == "HTTP_403"

    def test_validation_error_returns_422(self, test_app):
        # POST with invalid payload (missing required fields)
        resp = test_app.post("/test/validation", json={"wrong_field": "value"})
        assert resp.status_code == 422
        self._assert_error_schema(resp)
        body = resp.json()
        assert body["error"]["code"] == "VALIDATION_ERROR"
        assert isinstance(body["error"]["details"], list)
        assert len(body["error"]["details"]) > 0

    def test_validation_error_detail_has_field_key(self, test_app):
        resp = test_app.post("/test/validation", json={})
        assert resp.status_code == 422
        details = resp.json()["error"]["details"]
        # Each detail entry must have 'field', 'message', 'type'
        for detail in details:
            assert "field" in detail
            assert "message" in detail
            assert "type" in detail

    def test_unhandled_exception_returns_500(self, test_app):
        resp = test_app.get("/test/unhandled")
        assert resp.status_code == 500
        self._assert_error_schema(resp)
        assert resp.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"


# ---------------------------------------------------------------------------
# 6. Application Health Endpoints
# ---------------------------------------------------------------------------


class TestHealthEndpoints:
    """Verify root and health endpoints return correct schema and status."""

    @pytest.fixture(scope="class")
    def client(self):
        from app.main import app

        return TestClient(app, raise_server_exceptions=False)

    def test_root_endpoint_returns_200(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_root_endpoint_schema(self, client):
        resp = client.get("/")
        body = resp.json()
        for key in ("name", "version", "status", "message", "docs_url"):
            assert key in body, f"Missing key '{key}' in root response: {body}"

    def test_root_endpoint_name(self, client):
        resp = client.get("/")
        assert resp.json()["name"] == "Regal Fitness API"

    def test_root_endpoint_status_online(self, client):
        resp = client.get("/")
        assert resp.json()["status"] == "online"

    def test_root_health_endpoint_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_root_health_endpoint_schema(self, client):
        resp = client.get("/health")
        body = resp.json()
        for key in ("status", "version", "environment", "database", "database_details"):
            assert key in body, f"Missing key '{key}' in /health response: {body}"

    def test_root_health_database_details_has_status_key(self, client):
        resp = client.get("/health")
        db_details = resp.json()["database_details"]
        assert isinstance(db_details, dict)
        assert "status" in db_details

    def test_root_health_database_field_is_configured(self, client):
        resp = client.get("/health")
        # 'database' now reflects actual connectivity: 'connected' or 'disconnected'
        assert resp.json()["database"] in ("connected", "disconnected")

    def test_api_v1_health_endpoint_returns_200(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200

    def test_api_v1_health_endpoint_schema(self, client):
        resp = client.get("/api/v1/health")
        body = resp.json()
        for key in ("status", "version", "environment", "database"):
            assert key in body, f"Missing key '{key}' in /api/v1/health response: {body}"

    def test_api_v1_health_status_healthy(self, client):
        resp = client.get("/api/v1/health")
        # 'healthy' when DB connected; 'degraded' when DB offline — both are valid test states
        assert resp.json()["status"] in ("healthy", "degraded")

    def test_unknown_route_returns_404_error_schema(self, client):
        resp = client.get("/this/does/not/exist")
        assert resp.status_code == 404
        body = resp.json()
        assert "error" in body

    def test_docs_url_accessible(self, client):
        """OpenAPI docs endpoint must be accessible."""
        resp = client.get("/docs")
        assert resp.status_code == 200

    def test_openapi_json_accessible(self, client):
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert "openapi" in schema
        assert "paths" in schema


# ---------------------------------------------------------------------------
# 7. Application Lifespan (startup/shutdown without crash)
# ---------------------------------------------------------------------------


class TestLifespan:
    """Verify the application starts and shuts down cleanly even without DB."""

    def test_app_starts_without_crash(self):
        """
        Starting TestClient triggers lifespan startup.
        The app must not raise even if DB is offline.
        """
        from app.main import app

        # TestClient enters lifespan context on __enter__
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/")
            assert resp.status_code == 200

    def test_app_shuts_down_without_crash(self):
        """
        Exiting the TestClient context triggers lifespan shutdown.
        engine.dispose() must run cleanly.
        """
        from app.main import app

        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                client.get("/health")
            # If we reach here, shutdown completed without raising
        except Exception as exc:
            pytest.fail(f"Lifespan shutdown raised an exception: {exc}")

    def test_cors_middleware_configured(self):
        """CORS middleware must accept preflight requests from allowed origins."""
        from app.main import app

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.options(
                "/",
                headers={
                    "Origin": "http://localhost:3000",
                    "Access-Control-Request-Method": "GET",
                },
            )
            # Should not 405; preflight passes through CORS middleware
            assert resp.status_code in (200, 400)


# ---------------------------------------------------------------------------
# 8. Liveness and Readiness Probes
# ---------------------------------------------------------------------------


class TestLivenessProbe:
    """
    GET /health/live — process-level probe.
    Must return HTTP 200 regardless of database state.
    """

    @pytest.fixture(scope="class")
    def client(self):
        from app.main import app

        return TestClient(app, raise_server_exceptions=False)

    def test_liveness_returns_200(self, client):
        resp = client.get("/health/live")
        assert resp.status_code == 200

    def test_liveness_schema(self, client):
        resp = client.get("/health/live")
        body = resp.json()
        for key in ("status", "version", "environment"):
            assert key in body, f"Missing key '{key}' in /health/live response: {body}"

    def test_liveness_status_is_alive(self, client):
        resp = client.get("/health/live")
        assert resp.json()["status"] == "alive"

    def test_liveness_does_not_contain_database_key(self, client):
        """Liveness probe must not expose database details — no dependency checks."""
        resp = client.get("/health/live")
        body = resp.json()
        assert "database" not in body, (
            "Liveness probe must not include database details: "
            "it must pass even when PostgreSQL is unavailable."
        )

    def test_liveness_alive_when_db_offline(self):
        """
        Simulate DB being offline by patching check_db_connectivity.
        Liveness probe must still return HTTP 200.
        """
        from unittest.mock import patch
        from app.main import app

        # Even if the DB probe would raise, liveness must not call it at all
        with patch(
            "app.database.session.check_db_connectivity",
            side_effect=Exception("DB completely down"),
        ):
            with TestClient(app, raise_server_exceptions=False) as c:
                resp = c.get("/health/live")
        assert resp.status_code == 200
        assert resp.json()["status"] == "alive"

    def test_versioned_liveness_route_exists(self, client):
        """The liveness route must also be accessible via /api/v1/health/live."""
        resp = client.get("/api/v1/health/live")
        assert resp.status_code == 200
        assert resp.json()["status"] == "alive"


class TestReadinessProbe:
    """
    GET /health/ready — dependency-level probe.
    Returns HTTP 200 when PostgreSQL is reachable, HTTP 503 when not.
    """

    @pytest.fixture(scope="class")
    def client(self):
        from app.main import app

        return TestClient(app, raise_server_exceptions=False)

    def test_readiness_schema_always_present(self, client):
        """Response body must contain the required keys regardless of HTTP status."""
        resp = client.get("/health/ready")
        body = resp.json()
        for key in ("status", "version", "environment", "database"):
            assert key in body, f"Missing key '{key}' in /health/ready response: {body}"

    def test_readiness_status_field_known_value(self, client):
        resp = client.get("/health/ready")
        assert resp.json()["status"] in ("ready", "not_ready")

    def test_readiness_database_field_known_value(self, client):
        resp = client.get("/health/ready")
        assert resp.json()["database"] in ("connected", "disconnected")

    def test_readiness_503_when_db_offline(self):
        """
        When check_db_connectivity returns 'disconnected', the probe must
        return HTTP 503 and status='not_ready'.
        """
        from unittest.mock import patch
        from app.main import app

        disconnected = {
            "status": "disconnected",
            "dialect": "postgresql",
            "message": "Database server is unreachable or offline",
        }
        with patch("app.main.check_db_connectivity", return_value=disconnected), \
             patch("app.api.v1.endpoints.health.check_db_connectivity", return_value=disconnected):
            with TestClient(app, raise_server_exceptions=False) as c:
                resp = c.get("/health/ready")

        assert resp.status_code == 503, (
            f"Expected 503 when DB is offline, got {resp.status_code}"
        )
        body = resp.json()
        assert body["status"] == "not_ready"
        assert body["database"] == "disconnected"

    def test_readiness_503_body_has_database_details(self):
        """HTTP 503 response must still include database_details for diagnostics."""
        from unittest.mock import patch
        from app.main import app

        disconnected = {
            "status": "disconnected",
            "dialect": "postgresql",
            "message": "Database server is unreachable or offline",
        }
        with patch("app.main.check_db_connectivity", return_value=disconnected), \
             patch("app.api.v1.endpoints.health.check_db_connectivity", return_value=disconnected):
            with TestClient(app, raise_server_exceptions=False) as c:
                resp = c.get("/health/ready")

        body = resp.json()
        assert "database_details" in body
        assert body["database_details"]["status"] == "disconnected"

    def test_readiness_200_when_db_online(self):
        """
        When check_db_connectivity returns 'connected', the probe must
        return HTTP 200 and status='ready'.
        Both call sites (main.py and endpoints/health.py) must be patched
        because they import check_db_connectivity by name at module load time.
        """
        from unittest.mock import patch
        from app.main import app

        connected = {"status": "connected", "dialect": "postgresql"}
        with patch("app.main.check_db_connectivity", return_value=connected), \
             patch("app.api.v1.endpoints.health.check_db_connectivity", return_value=connected):
            with TestClient(app, raise_server_exceptions=False) as c:
                resp = c.get("/health/ready")

        assert resp.status_code == 200, (
            f"Expected 200 when DB is online, got {resp.status_code}"
        )
        body = resp.json()
        assert body["status"] == "ready"
        assert body["database"] == "connected"

    def test_versioned_readiness_route_exists(self, client):
        """The readiness route must also be accessible via /api/v1/health/ready."""
        resp = client.get("/api/v1/health/ready")
        assert resp.status_code in (200, 503)  # Either state is valid; route must exist
        body = resp.json()
        assert body["status"] in ("ready", "not_ready")


class TestApiV1HealthHonestStatus:
    """
    GET /api/v1/health — verify honest status reporting.
    'healthy' only when DB is connected; 'degraded' when DB is offline.
    """

    def test_degraded_status_when_db_offline(self):
        from unittest.mock import patch
        from app.main import app

        disconnected = {
            "status": "disconnected",
            "dialect": "postgresql",
            "message": "Database server is unreachable or offline",
        }
        with patch("app.main.check_db_connectivity", return_value=disconnected), \
             patch("app.api.v1.endpoints.health.check_db_connectivity", return_value=disconnected):
            with TestClient(app, raise_server_exceptions=False) as c:
                resp = c.get("/api/v1/health")

        assert resp.status_code == 200  # Still HTTP 200 — application is running
        body = resp.json()
        assert body["status"] == "degraded", (
            f"Expected 'degraded' when DB offline, got '{body['status']}'"
        )
        assert body["database"] == "disconnected"

    def test_healthy_status_when_db_online(self):
        from unittest.mock import patch
        from app.main import app

        connected = {"status": "connected", "dialect": "postgresql"}
        with patch("app.main.check_db_connectivity", return_value=connected), \
             patch("app.api.v1.endpoints.health.check_db_connectivity", return_value=connected):
            with TestClient(app, raise_server_exceptions=False) as c:
                resp = c.get("/api/v1/health")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "healthy"
        assert body["database"] == "connected"

    def test_root_health_degraded_when_db_offline(self):
        """Root /health must also report 'degraded' when DB is offline."""
        from unittest.mock import patch
        from app.main import app

        disconnected = {
            "status": "disconnected",
            "dialect": "postgresql",
            "message": "Database server is unreachable or offline",
        }
        with patch("app.main.check_db_connectivity", return_value=disconnected), \
             patch("app.api.v1.endpoints.health.check_db_connectivity", return_value=disconnected):
            with TestClient(app, raise_server_exceptions=False) as c:
                resp = c.get("/health")

        assert resp.status_code == 200
        assert resp.json()["status"] == "degraded"

    def test_root_health_healthy_when_db_online(self):
        from unittest.mock import patch
        from app.main import app

        connected = {"status": "connected", "dialect": "postgresql"}
        with patch("app.main.check_db_connectivity", return_value=connected), \
             patch("app.api.v1.endpoints.health.check_db_connectivity", return_value=connected):
            with TestClient(app, raise_server_exceptions=False) as c:
                resp = c.get("/health")

        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"
