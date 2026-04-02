"""Tests for OpenAPI schema and Swagger docs endpoints."""

from __future__ import annotations

import pytest
from django.test import Client


@pytest.mark.django_db
class TestSchemaEndpoints:
    """Tests for authenticated schema and docs routes."""

    def test_schema_returns_200(self, admin_client: Client) -> None:
        """GET /api/schema/ returns HTTP 200 for authenticated users."""
        response = admin_client.get("/api/schema/")
        assert response.status_code == 200

    def test_schema_returns_json(self, admin_client: Client) -> None:
        """GET /api/schema/ returns an OpenAPI JSON payload."""
        response = admin_client.get("/api/schema/")
        assert response.status_code == 200
        content_type = response["Content-Type"]
        assert (
            "application/vnd.oai.openapi+json" in content_type
            or "application/vnd.oai.openapi" in content_type
            or "application/json" in content_type
        )

    def test_docs_returns_200(self, admin_client: Client) -> None:
        """GET /api/docs/ returns HTTP 200 for authenticated users."""
        response = admin_client.get("/api/docs/")
        assert response.status_code == 200

    def test_docs_returns_html(self, admin_client: Client) -> None:
        """GET /api/docs/ returns an HTML response."""
        response = admin_client.get("/api/docs/")
        assert response.status_code == 200
        assert "text/html" in response["Content-Type"]

    def test_schema_rejects_unauthenticated(
        self, unauthenticated_client: Client
    ) -> None:
        """GET /api/schema/ returns 401 without IIS authentication."""
        response = unauthenticated_client.get("/api/schema/")
        assert response.status_code == 401

    def test_docs_rejects_unauthenticated(self, unauthenticated_client: Client) -> None:
        """GET /api/docs/ returns 401 without IIS authentication."""
        response = unauthenticated_client.get("/api/docs/")
        assert response.status_code == 401
