from fastapi.testclient import TestClient


def test_root_endpoint(client: TestClient) -> None:
    """
    Test GET / returns 200 and expected status metadata.
    """
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Regal Fitness API"
    assert data["version"] == "1.0.0"
    assert data["status"] == "online"
    assert data["docs_url"] == "/docs"


def test_health_endpoint(client: TestClient) -> None:
    """
    Test GET /health returns 200.
    With PostgreSQL offline, status is 'degraded' and database is 'disconnected'.
    With PostgreSQL online, status is 'healthy' and database is 'connected'.
    """
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    # Honest reporting: status reflects actual DB state
    assert data["status"] in ("healthy", "degraded")
    assert data["version"] == "1.0.0"
    assert data["database"] in ("connected", "disconnected")
    assert "environment" in data
    assert "database_details" in data


def test_api_v1_health_endpoint(client: TestClient) -> None:
    """
    Test GET /api/v1/health returns 200 through modular router.
    Status reflects actual database connectivity.
    """
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("healthy", "degraded")
    assert data["version"] == "1.0.0"


def test_docs_and_openapi_endpoints(client: TestClient) -> None:
    """
    Verify Swagger documentation and OpenAPI schema endpoints are accessible.
    """
    docs_response = client.get("/docs")
    assert docs_response.status_code == 200

    openapi_response = client.get("/openapi.json")
    assert openapi_response.status_code == 200
    schema = openapi_response.json()
    assert schema["info"]["title"] == "Regal Fitness API"
    assert schema["info"]["version"] == "1.0.0"


def test_cors_headers(client: TestClient) -> None:
    """
    Verify configured CORS origins are permitted in headers.
    """
    headers = {
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "GET",
    }
    response = client.get("/health", headers=headers)
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
