"""Tests for the health check endpoint."""

from __future__ import annotations

import pytest
from django.test import Client


class TestHealthView:
    """Tests for the health check view."""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Set up test client and force IIS mode (no DB auth side effects)."""
        monkeypatch.setenv("AUTH_MODE", "iis")
        self.client = Client()

    def test_health_returns_200(self) -> None:
        """GET /api/health/ returns HTTP 200 status code."""
        response = self.client.get("/api/health/")
        assert response.status_code == 200

    def test_health_returns_status_ok(self) -> None:
        """GET /api/health/ returns response body with status=ok."""
        response = self.client.get("/api/health/")
        assert response.json() == {"status": "ok"}

    def test_health_allows_unauthenticated_access(self) -> None:
        """GET /api/health/ succeeds without REMOTE_USER header."""
        # Ensure no REMOTE_USER is set and request still succeeds
        response = self.client.get("/api/health/")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_health_response_has_public_cache_header(self) -> None:
        """GET /api/health/ returns short-lived public cache directives."""
        response = self.client.get("/api/health/")
        cache_control = response.headers.get("Cache-Control", "")
        assert "public" in cache_control
        assert "max-age=5" in cache_control

    def test_health_method_not_allowed_post(self) -> None:
        """POST /api/health/ returns HTTP 405 Method Not Allowed."""
        response = self.client.post("/api/health/")
        assert response.status_code == 405

    def test_health_method_not_allowed_put(self) -> None:
        """PUT /api/health/ returns HTTP 405 Method Not Allowed."""
        response = self.client.put("/api/health/")
        assert response.status_code == 405

    def test_health_method_not_allowed_delete(self) -> None:
        """DELETE /api/health/ returns HTTP 405 Method Not Allowed."""
        response = self.client.delete("/api/health/")
        assert response.status_code == 405
