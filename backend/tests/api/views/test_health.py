"""Tests for the health check endpoint."""

from __future__ import annotations

import pytest
from django.core.cache import cache
from django.conf import settings
from django.test import Client

import api.views.health as health_module
from api.views.health import HealthView


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

    def test_health_returns_status_version_and_uptime(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """GET /api/health/ returns status, version, and uptime."""
        monkeypatch.setattr(health_module, "PROCESS_START_MONOTONIC", 100.0)
        monkeypatch.setattr(health_module.time, "monotonic", lambda: 112.9)

        response = self.client.get("/api/health/")
        assert response.json() == {
            "status": "ok",
            "version": settings.API_VERSION,
            "uptime_seconds": 12,
        }

    def test_health_allows_unauthenticated_access(self) -> None:
        """GET /api/health/ succeeds without REMOTE_USER header."""
        # Ensure no REMOTE_USER is set and request still succeeds
        response = self.client.get("/api/health/")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ok"
        assert payload["version"] == settings.API_VERSION
        assert isinstance(payload["uptime_seconds"], int)
        assert payload["uptime_seconds"] >= 0

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

    def test_health_returns_429_when_throttled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Second rapid request returns 429 with standard error envelope."""
        cache.clear()
        monkeypatch.setattr(HealthView, "_throttle_rate", "1/minute")

        first = self.client.get("/api/health/")
        second = self.client.get("/api/health/")

        assert first.status_code == 200
        assert second.status_code == 429
        payload = second.json()
        assert "throttled" in payload["detail"].lower()
        assert "request_id" in payload

    def test_health_throttle_includes_retry_after(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """429 response includes a Retry-After header."""
        cache.clear()
        monkeypatch.setattr(HealthView, "_throttle_rate", "1/minute")

        self.client.get("/api/health/")
        response = self.client.get("/api/health/")

        assert response.status_code == 429
        assert response["Retry-After"].isdigit()
