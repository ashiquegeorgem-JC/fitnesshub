from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.schemas.health import RootResponse, HealthResponse
from app.api.v1.api import api_router

# Initialize FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Backend API for Regal Fitness commercial gym management platform.",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

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


@app.get("/health", response_model=HealthResponse, tags=["Health"])
def health_check() -> HealthResponse:
    """
    Direct health check endpoint verifying application readiness.
    """
    return HealthResponse(
        status="healthy",
        version=settings.APP_VERSION,
        environment=settings.APP_ENV,
        database="configured",
    )


# Include API v1 router under configured prefix
app.include_router(api_router, prefix=settings.API_V1_STR)
