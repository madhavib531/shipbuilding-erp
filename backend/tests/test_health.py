"""Tests for health check endpoints."""

import pytest


def test_root_endpoint(client):
    """Test root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "version" in data


def test_health_check(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["message"] == "Backend service is operational"
    assert data["version"]
    assert "database" in data


def test_openapi_docs(client):
    """Test OpenAPI documentation is available."""
    response = client.get("/api/docs")
    assert response.status_code == 200
    assert "swagger" in response.text.lower()


def test_materials_list_endpoint(client):
    """Test materials list endpoint (Phase 1 stub)."""
    response = client.get("/api/v1/materials")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "data" in data


def test_health_hides_database_error_details(client):
    from app.database import get_db
    from app.main import app

    class FailingSession:
        def execute(self, *args, **kwargs):
            raise RuntimeError('connection to server at "db.internal", port 5432 failed: password authentication failed for user "secret_user"')

    previous = app.dependency_overrides[get_db]
    app.dependency_overrides[get_db] = lambda: FailingSession()
    try:
        data = client.get("/health").json()
    finally:
        app.dependency_overrides[get_db] = previous
    assert data["database"] == "unavailable"
    assert "secret_user" not in str(data) and "db.internal" not in str(data)
