import os
import sys
import pytest
from fastapi.testclient import TestClient

# Ensure backend directory is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app


@pytest.fixture(scope="session")
def client() -> TestClient:
    """
    TestClient fixture for making API requests in integration and unit tests.
    """
    with TestClient(app) as test_client:
        yield test_client
