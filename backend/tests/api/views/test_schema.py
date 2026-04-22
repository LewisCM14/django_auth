"""Tests for OpenAPI schema and Swagger docs endpoints."""

from __future__ import annotations

import pytest
from django.core.cache import cache
from django.test import Client

from api.views.docs import SchemaView, SwaggerDocsView


class TestSchemaEndpoints:
    """Tests for authenticated schema and docs routes."""

    @pytest.mark.django_db
    def test_schema_returns_200(self, admin_client: Client) -> None:
        """GET /api/schema/ returns HTTP 200 for authenticated users."""
        response = admin_client.get("/api/schema/")
        assert response.status_code == 200

    @pytest.mark.django_db
    def test_schema_returns_json(self, admin_client: Client) -> None:
        """GET /api/schema/ returns an OpenAPI JSON payload."""
        response = admin_client.get("/api/schema/")
        assert response.status_code == 200
        assert "default-src 'none'" in response.headers.get(
            "Content-Security-Policy", ""
        )
        content_type = response["Content-Type"]
        assert (
            "application/vnd.oai.openapi+json" in content_type
            or "application/vnd.oai.openapi" in content_type
            or "application/json" in content_type
        )

    @pytest.mark.django_db
    def test_schema_includes_health_and_user_paths(self, admin_client: Client) -> None:
        """GET /api/schema/ includes the application endpoints."""
        response = admin_client.get("/api/schema/")
        assert response.status_code == 200
        assert b"/api/health/" in response.content
        assert b"/api/user/" in response.content

    @pytest.mark.django_db
    def test_docs_returns_200(self, admin_client: Client) -> None:
        """GET /api/docs/ returns HTTP 200 for authenticated users."""
        response = admin_client.get("/api/docs/")
        assert response.status_code == 200

    @pytest.mark.django_db
    def test_docs_returns_html(self, admin_client: Client) -> None:
        """GET /api/docs/ returns an HTML response."""
        response = admin_client.get("/api/docs/")
        assert response.status_code == 200
        assert "text/html" in response["Content-Type"]
        assert "default-src 'none'" in response.headers.get(
            "Content-Security-Policy", ""
        )

    @pytest.mark.django_db
    def test_docs_uses_local_sidecar_assets(self, admin_client: Client) -> None:
        """GET /api/docs/ uses bundled Swagger UI assets instead of a CDN."""
        response = admin_client.get("/api/docs/")
        assert response.status_code == 200
        assert b"cdn.jsdelivr.net" not in response.content
        assert b"drf_spectacular_sidecar" in response.content
        assert b"SwaggerUIBundle(" not in response.content
        assert b"<style>" not in response.content

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

    @pytest.mark.django_db
    def test_schema_returns_429_when_throttled(
        self, admin_client: Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Second rapid schema request returns 429."""
        cache.clear()
        monkeypatch.setattr(SchemaView, "_throttle_rate", "1/minute")

        first = admin_client.get("/api/schema/")
        second = admin_client.get("/api/schema/")

        assert first.status_code == 200
        assert second.status_code == 429

    @pytest.mark.django_db
    def test_schema_throttle_includes_retry_after(
        self, admin_client: Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Schema 429 response includes a Retry-After header."""
        cache.clear()
        monkeypatch.setattr(SchemaView, "_throttle_rate", "1/minute")

        admin_client.get("/api/schema/")
        response = admin_client.get("/api/schema/")

        assert response.status_code == 429
        assert response["Retry-After"].isdigit()

    @pytest.mark.django_db
    def test_docs_returns_429_when_throttled(
        self, admin_client: Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Second rapid docs request returns 429."""
        cache.clear()
        monkeypatch.setattr(SwaggerDocsView, "_throttle_rate", "1/minute")

        first = admin_client.get("/api/docs/")
        second = admin_client.get("/api/docs/")

        assert first.status_code == 200
        assert second.status_code == 429

    @pytest.mark.django_db
    def test_docs_throttle_includes_retry_after(
        self, admin_client: Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Docs 429 response includes a Retry-After header."""
        cache.clear()
        monkeypatch.setattr(SwaggerDocsView, "_throttle_rate", "1/minute")

        admin_client.get("/api/docs/")
        response = admin_client.get("/api/docs/")

        assert response.status_code == 429
        assert response["Retry-After"].isdigit()
