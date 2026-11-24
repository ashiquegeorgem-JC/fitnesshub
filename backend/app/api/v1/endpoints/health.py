from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.database.session import check_db_connectivity
from app.schemas.health import HealthResponse, LivenessResponse, ReadinessResponse

router = APIRouter()


@router.get(
    "/health/live",
    response_model=LivenessResponse,
    tags=["Health"],
    summary="Liveness probe",
    description=(
        "Checks whether the application process is alive. "
        "Returns HTTP 200 as long as the process is running. "
        "Does NOT require a database connection."
    ),
)
def get_liveness() -> LivenessResponse:
    """
    Liveness probe — answers: 'Is the process up?'

    Used by container orchestrators (Kubernetes liveness probe, Railway health checks)
    to decide whether to restart the container. Never checks external dependencies.
    """
    return LivenessResponse(
        status="alive",
        version=settings.APP_VERSION,
        environment=settings.APP_ENV,
    )


@router.get(
    "/health/ready",
    tags=["Health"],
    summary="Readiness probe",
    description=(
        "Checks whether all required dependencies are operational. "
        "Returns HTTP 200 when ready, HTTP 503 when PostgreSQL is unavailable."
    ),
)
def get_readiness() -> JSONResponse:
    """
    Readiness probe — answers: 'Is the application ready to serve traffic?'

    Used by load balancers and orchestrators to decide whether to route traffic.
    Returns HTTP 503 (Service Unavailable) when PostgreSQL is disconnected so that
    the router can redirect traffic to a healthy replica or display a maintenance page.
    """
    db_info = check_db_connectivity()
    db_connected = db_info.get("status") == "connected"

    payload = ReadinessResponse(
        status="ready" if db_connected else "not_ready",
        version=settings.APP_VERSION,
        environment=settings.APP_ENV,
        database=db_info.get("status", "unknown"),
        database_details=db_info,
    )

    http_status = 200 if db_connected else 503
    return JSONResponse(
        status_code=http_status,
        content=payload.model_dump(),
    )


@router.get(
    "/health",
    response_model=HealthResponse,
    tags=["Health"],
    summary="API health status",
    description=(
        "Reports overall application and database status. "
        "status='healthy' only when PostgreSQL is connected. "
        "status='degraded' when the application is running but the database is offline."
    ),
)
def get_health() -> HealthResponse:
    """
    General health endpoint — reports both application runtime and database state honestly.

    Unlike the liveness probe, this endpoint probes PostgreSQL and surfaces its
    connectivity status. The 'status' field reflects the true system state:
      - 'healthy'  → process running AND database connected
      - 'degraded' → process running BUT database disconnected
    """
    db_info = check_db_connectivity()
    db_connected = db_info.get("status") == "connected"

    return HealthResponse(
        status="healthy" if db_connected else "degraded",
        version=settings.APP_VERSION,
        environment=settings.APP_ENV,
        database=db_info.get("status", "unknown"),
        database_details=db_info,
    )
