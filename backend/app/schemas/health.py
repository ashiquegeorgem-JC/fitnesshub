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
                "message": "Welcome to Regal Fitness Backend API",
                "docs_url": "/docs",
            }
        }
    )


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    database: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "healthy",
                "version": "1.0.0",
                "environment": "development",
                "database": "configured",
            }
        }
    )
