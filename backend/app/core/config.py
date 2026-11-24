import json
from typing import List, Optional, Union
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Known insecure development placeholder secrets that must never reach production.
_INSECURE_JWT_DEFAULTS = frozenset({
    "regal_fitness_default_dev_jwt_secret_key_change_in_production_32bytes",
    "secret",
    "changeme",
    "jwt_secret",
})

_INSECURE_HMAC_DEFAULTS = frozenset({
    "regal_fitness_default_dev_hmac_secret_key",
    "secret",
    "changeme",
    "otp_secret",
})

# SMS providers that must never be used in production.
_DEVELOPMENT_SMS_PROVIDERS = frozenset({"mock", "console"})


class Settings(BaseSettings):
    """
    Application Settings loaded from environment variables and .env files.
    Pydantic Settings validates data types and provides typed access.

    Production safety:
    - JWT_SECRET_KEY and OTP_HMAC_SECRET must be strong secrets (≥32 chars,
      not matching known development defaults) when APP_ENV is 'production'
      or 'prod'. Application startup is aborted if validation fails.
    - SMS_PROVIDER must not be 'mock' or 'console' in production.
    """

    # Application Metadata
    APP_NAME: str = "Regal Fitness API"
    APP_VERSION: str = "1.0.0"
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    API_V1_STR: str = "/api/v1"
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Logging Configuration
    LOG_LEVEL: str = "INFO"

    # Security Configuration
    OTP_HMAC_SECRET: str = "regal_fitness_default_dev_hmac_secret_key"
    JWT_SECRET_KEY: str = (
        "regal_fitness_default_dev_jwt_secret_key_change_in_production_32bytes"
    )
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 15
    OTP_EXPIRE_MINUTES: int = 10
    OTP_COOLDOWN_SECONDS: int = 60
    OTP_MAX_ATTEMPTS: int = 3

    # Rate Limiting Configuration
    LOGIN_RATE_LIMIT_MAX_ATTEMPTS: int = 5
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: int = 300  # 5 minutes
    OTP_VERIFY_RATE_LIMIT_MAX_ATTEMPTS: int = 10
    OTP_VERIFY_RATE_LIMIT_WINDOW_SECONDS: int = 60

    # Trusted Proxy Configuration
    # Comma-separated list of trusted reverse-proxy IPs (IPv4 or IPv6).
    # X-Forwarded-For is only honoured when the direct TCP peer (request.client.host)
    # appears in this list. Leave empty to always use the direct connection IP.
    # Example: "10.0.0.1,172.16.0.1,::1"
    TRUSTED_PROXY_IPS: str = ""

    # SMS Configuration
    SMS_PROVIDER: str = "mock"  # "mock", "console", "twilio"
    TWILIO_ACCOUNT_SID: Optional[str] = None
    TWILIO_AUTH_TOKEN: Optional[str] = None
    TWILIO_FROM_NUMBER: Optional[str] = None

    # Integration Switches
    WHATSAPP_AUTOMATION_ENABLED: bool = False

    # CORS Configuration
    ALLOWED_CORS_ORIGINS: Union[List[str], str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # Database Configuration (PostgreSQL)
    DATABASE_URL: str = (
        "postgresql+psycopg2://postgres:postgres@localhost:5432/regal_fitness_db"
    )
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30
    DB_ECHO: bool = False

    @field_validator("ALLOWED_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            v_trimmed = v.strip()
            if v_trimmed.startswith("[") and v_trimmed.endswith("]"):
                try:
                    parsed = json.loads(v_trimmed)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed if item]
                except json.JSONDecodeError:
                    pass
            # Comma-separated fallback
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        elif isinstance(v, list):
            return [str(item).strip() for item in v if item]
        return []

    def validate_production_security(self) -> None:
        """
        Abort startup in production if security-critical settings use known
        development defaults, are too short, or use non-production SMS providers.
        Called on application startup in lifespan.
        """
        is_prod = self.APP_ENV.lower() in ("production", "prod")
        if not is_prod:
            return

        errors: list[str] = []

        # JWT secret validation
        if self.JWT_SECRET_KEY in _INSECURE_JWT_DEFAULTS:
            errors.append(
                "JWT_SECRET_KEY is set to a known insecure development placeholder. "
                "Generate a secure random secret: openssl rand -hex 32"
            )
        elif len(self.JWT_SECRET_KEY) < 32:
            errors.append(
                f"JWT_SECRET_KEY is too short ({len(self.JWT_SECRET_KEY)} chars). "
                "Must be at least 32 characters in production."
            )

        # OTP HMAC secret validation
        if self.OTP_HMAC_SECRET in _INSECURE_HMAC_DEFAULTS:
            errors.append(
                "OTP_HMAC_SECRET is set to a known insecure development placeholder. "
                "Generate a secure random secret: openssl rand -hex 32"
            )
        elif len(self.OTP_HMAC_SECRET) < 32:
            errors.append(
                f"OTP_HMAC_SECRET is too short ({len(self.OTP_HMAC_SECRET)} chars). "
                "Must be at least 32 characters in production."
            )

        # SMS provider validation
        if self.SMS_PROVIDER.lower().strip() in _DEVELOPMENT_SMS_PROVIDERS:
            errors.append(
                f"SMS_PROVIDER='{self.SMS_PROVIDER}' is a development-only provider. "
                "Set SMS_PROVIDER=twilio (or another production provider) in production. "
                "Using a mock/console provider silently swallows OTPs without delivery."
            )

        if errors:
            error_list = "\n  - ".join(errors)
            raise ValueError(
                f"[SECURITY] Application startup blocked in production environment "
                f"due to insecure configuration:\n  - {error_list}"
            )

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() in ("production", "prod")

    @property
    def trusted_proxy_ip_set(self) -> frozenset:
        """Return the set of trusted proxy IPs parsed from TRUSTED_PROXY_IPS."""
        if not self.TRUSTED_PROXY_IPS.strip():
            return frozenset()
        return frozenset(
            ip.strip() for ip in self.TRUSTED_PROXY_IPS.split(",") if ip.strip()
        )

    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
