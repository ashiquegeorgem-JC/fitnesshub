from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict


class RootResponse(BaseModel):
    name: str
    version: str
    status: str
    message: str
    docs_url: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Regal Fitness API",
                "version": "1.0.0",
                "status": "online",
                "message": "Regal Fitness API is operational",
                "docs_url": "/docs",
            }
        }
    )


class LivenessResponse(BaseModel):
    """
    Response schema for GET /health/live.
    Signals only that the application process is running.
    Database connectivity is intentionally excluded.
    """

    status: str  # Always "alive" when the process is up
    version: str
    environment: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "alive",
                "version": "1.0.0",
                "environment": "development",
            }
        }
    )


class ReadinessResponse(BaseModel):
    """
    Response schema for GET /health/ready.
    HTTP 200 = all required dependencies are operational.
    HTTP 503 = one or more required dependencies are unavailable.
    """

    status: str  # "ready" | "not_ready"
    version: str
    environment: str
    database: str  # "connected" | "disconnected"
    database_details: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "ready",
                "version": "1.0.0",
                "environment": "development",
                "database": "connected",
                "database_details": {
                    "status": "connected",
                    "dialect": "postgresql",
                },
            }
        }
    )


class HealthResponse(BaseModel):
    """
    Response schema for GET /api/v1/health.
    Reports both application and database status honestly.
    status = "healthy" only when all dependencies are connected.
    status = "degraded" when the application is running but DB is offline.
    """

    status: str  # "healthy" | "degraded"
    version: str
    environment: str
    database: str  # "connected" | "disconnected"
    database_details: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "healthy",
                "version": "1.0.0",
                "environment": "development",
                "database": "connected",
                "database_details": {
                    "status": "connected",
                    "dialect": "postgresql",
                },
            }
        }
    )
