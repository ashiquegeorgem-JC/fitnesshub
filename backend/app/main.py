from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.api import api_router
from app.core.config import settings
from app.core.handlers import register_exception_handlers
from app.core.logging import logger, setup_logging
from app.database.session import check_db_connectivity, engine
from app.schemas.health import HealthResponse, LivenessResponse, ReadinessResponse, RootResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application startup and shutdown lifecycle management.
    """
    # Startup actions
    setup_logging()
    # Validate production security settings — aborts startup if insecure
    settings.validate_production_security()
    logger.info(
        f"Starting {settings.APP_NAME} v{settings.APP_VERSION} [{settings.APP_ENV}]"
    )
    db_status = check_db_connectivity()
    logger.info(
        f"Database connectivity status: {db_status['status']} "
        f"(dialect: {db_status.get('dialect', 'unknown')})"
    )

    yield

    # Shutdown actions
    logger.info(f"Shutting down {settings.APP_NAME}...")
    engine.dispose()
    logger.info("Database connection pool disposed cleanly.")


# Initialize FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Backend API for Regal Fitness commercial gym management platform.",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Register centralized exception handlers
register_exception_handlers(app)

# Configure CORS middleware using environment-driven origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_model=RootResponse, tags=["General"])
def root() -> RootResponse:
    """
    Root endpoint returning general API status and metadata.
    """
    return RootResponse(
        name=settings.APP_NAME,
        version=settings.APP_VERSION,
        status="online",
        message="Regal Fitness API is operational",
        docs_url="/docs",
    )


@app.get(
    "/health/live",
    response_model=LivenessResponse,
    tags=["Health"],
    summary="Liveness probe",
    description="Checks whether the application process is running. Does not require a database connection.",
)
def liveness_check() -> LivenessResponse:
    """
    Liveness probe — answers: 'Is the process up?'
    Returns HTTP 200 as long as the process is running. No external dependency checks.
    """
    return LivenessResponse(
        status="alive",
        version=settings.APP_VERSION,
        environment=settings.APP_ENV,
    )


@app.get(
    "/health/ready",
    tags=["Health"],
    summary="Readiness probe",
    description="Checks PostgreSQL connectivity. Returns HTTP 200 when ready, HTTP 503 when database is unavailable.",
)
def readiness_check() -> JSONResponse:
    """
    Readiness probe — answers: 'Is the application ready to serve traffic?'
    Returns HTTP 503 when PostgreSQL is disconnected.
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
    return JSONResponse(
        status_code=200 if db_connected else 503,
        content=payload.model_dump(),
    )


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["Health"],
    summary="Application health status",
    description=(
        "Reports application and database status. "
        "status='healthy' only when PostgreSQL is connected. "
        "status='degraded' when the database is offline."
    ),
)
def health_check() -> HealthResponse:
    """
    General health endpoint — honest reporting of system state.
    status='healthy' → process running AND database connected.
    status='degraded' → process running BUT database disconnected.
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


# Include API v1 router under configured prefix
app.include_router(api_router, prefix=settings.API_V1_STR)
