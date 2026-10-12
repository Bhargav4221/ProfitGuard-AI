"""Tests for Health Endpoint, Route Registration, and OpenAPI Schema Generation."""

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.main import app, get_all_registered_endpoints


def test_health_endpoint_healthy(client: TestClient):
    """Verifies that /healthz returns status healthy and database connected."""
    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    assert data["service"] == "ProfitGuard AI"


def test_health_endpoint_db_failure_returns_503(client: TestClient):
    """Verifies that when database connectivity fails, /healthz returns 503 with clear error."""
    from app.core.database import get_db

    def failing_db():
        mock_session = MagicMock()
        mock_session.execute.side_effect = OperationalError("connection refused", {}, None)
        yield mock_session

    app.dependency_overrides[get_db] = failing_db
    try:
        response = client.get("/healthz")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"
        assert "unreachable" in data["database"]
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_openapi_schema_contains_all_core_endpoints(client: TestClient):
    """Verifies that app.openapi() registers all expected endpoints across all modules."""
    schema = app.openapi()
    assert schema["info"]["title"] == "ProfitGuard AI"
    paths = schema.get("paths", {})

    expected_endpoints = [
        # Health
        "/healthz",
        # Auth
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
        "/api/v1/auth/me",
        # Organizations
        "/api/v1/orgs",
        "/api/v1/orgs/{org_id}",
        "/api/v1/orgs/{org_id}/members/invite",
        "/api/v1/orgs/{org_id}/members/{user_id}/role",
        # Economics & Audit
        "/api/v1/economics",
        "/api/v1/audit",
        "/api/v1/audit/verify",
        # Orders & Line Items
        "/api/v1/orders",
        "/api/v1/orders/{order_id}",
        "/api/v1/orders/{order_id}/items",
        # Decision Engine
        "/api/v1/orders/{order_id}/evaluate",
        "/api/v1/orders/{order_id}/decision",
        "/api/v1/orders/{order_id}/intervention-outcome",
        # Reconciliation
        "/api/v1/orders/{order_id}/reconciliation",
        "/api/v1/orders/{order_id}/reconcile",
        # CSV Import
        "/api/v1/csv-import/template",
        "/api/v1/csv-import/preview",
        "/api/v1/csv-import/commit",
        "/api/v1/csv-import/history",
        "/api/v1/csv-import/history/{import_id}",
        # Delivery & NDR
        "/api/v1/delivery/events",
        "/api/v1/delivery/simulate",
        "/api/v1/delivery/webhook",
        "/api/v1/delivery/events/{order_id}",
        "/api/v1/delivery/ndr",
        "/api/v1/delivery/ndr/{case_id}",
        "/api/v1/delivery/ndr/{case_id}/actions",
        "/api/v1/delivery/ndr/{case_id}/recommendation",
        # Demo Harness
        "/api/v1/demo/seed",
        "/api/v1/demo/reset",
        "/api/v1/demo/run-journey",
    ]

    for endpoint in expected_endpoints:
        assert endpoint in paths, f"Missing endpoint in OpenAPI schema: {endpoint}"


def test_app_routes_iterable_without_methods_attribute_error():
    """Verifies that iterating over app.routes does not raise AttributeError on _IncludedRouter."""
    routes_inspected = []
    for route in app.routes:
        # Must have path and methods attributes without raising AttributeError
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        routes_inspected.append((path, methods))

    assert len(routes_inspected) >= 6
    # Ensure all routes had non-null path and methods
    for p, m in routes_inspected:
        assert p is not None
        assert m is not None


def test_get_all_registered_endpoints_helper():
    """Verifies that the get_all_registered_endpoints helper returns complete structured data."""
    endpoints = get_all_registered_endpoints()
    assert len(endpoints) >= 37
    paths = {ep["path"] for ep in endpoints}
    assert "/healthz" in paths
    assert "/api/v1/orders" in paths
    assert "/api/v1/demo/run-journey" in paths
