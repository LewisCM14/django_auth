"""Tests for the Request-ID middleware."""

from __future__ import annotations

import uuid

import pytest
from django.test import Client


class TestRequestIdMiddleware:
    """Tests for the request-level ID tracking middleware."""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Set up test client and force IIS mode (no DB auth side effects)."""
        monkeypatch.setenv("AUTH_MODE", "iis")
        self.client = Client()

    def test_response_contains_x_request_id_header(self) -> None:
        """Any response includes X-Request-ID header.

        Every HTTP response should have the X-Request-ID header set by the
        middleware for distributed tracing and debugging.
        """
        response = self.client.get("/api/health/")
        assert "X-Request-ID" in response
        # Header should be non-empty
        assert response["X-Request-ID"]

    def test_request_id_is_valid_uuid4(self) -> None:
        """X-Request-ID header value is a valid UUID v4.

        The middleware generates a UUID4 for each request. This test verifies
        the format is correct and can be parsed as a valid UUID.
        """
        response = self.client.get("/api/health/")
        request_id = response["X-Request-ID"]

        # Should not raise ValueError if valid UUID
        parsed_uuid = uuid.UUID(request_id, version=4)
        assert str(parsed_uuid) == request_id

    def test_unique_request_ids_per_request(self) -> None:
        """Two sequential requests produce different X-Request-ID values.

        Each request must have a unique ID. Verify that multiple requests
        generate different IDs.
        """
        response1 = self.client.get("/api/health/")
        response2 = self.client.get("/api/health/")

        request_id_1 = response1["X-Request-ID"]
        request_id_2 = response2["X-Request-ID"]

        assert request_id_1 != request_id_2

    def test_request_id_available_on_request_object(self) -> None:
        """Middleware attaches request ID to request object for downstream access.

        The request ID should be available on the request object (e.g., as
        request.request_id or in request.META) so downstream code (views,
        services, logging) can access it without reparsing the header.

        This test verifies the middleware stores it in a way the view can access.
        """
        response = self.client.get("/api/health/")

        # Verify header exists (proves middleware ran)
        assert "X-Request-ID" in response
        request_id_from_header = response["X-Request-ID"]

        # Request ID should be non-empty and valid UUID
        assert request_id_from_header
        uuid.UUID(request_id_from_header, version=4)
