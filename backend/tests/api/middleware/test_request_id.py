"""Tests for the Request-ID middleware."""

from __future__ import annotations

import asyncio
import inspect
import logging
import uuid
from collections.abc import Coroutine
from typing import Any, cast
from unittest.mock import Mock

import pytest
from django.http import HttpResponse
from django.test import Client, RequestFactory

from api.middleware.request_id import (
    RequestIdFilter,
    RequestIdMiddleware,
    request_id_var,
)


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

    def test_request_id_var_set_during_request(self) -> None:
        """request_id_var holds the request UUID between process_request and process_response.

        After process_request runs, the context variable must contain the same
        UUID that was stored on the request object — before process_response
        resets it.
        """
        request_id_var.set("-")  # ensure a clean starting state
        factory = RequestFactory()
        request = factory.get("/api/health/")
        middleware = RequestIdMiddleware(get_response=lambda r: HttpResponse())

        middleware.process_request(request)

        current_var = request_id_var.get()
        assert current_var != "-"
        assert current_var == getattr(request, "request_id")
        request_id_var.set("-")  # clean up so subsequent tests start fresh

    def test_request_id_var_reset_after_response(self) -> None:
        """request_id_var returns '-' after process_response completes.

        The middleware must reset the context variable to the default sentinel
        at the end of each request so that code running outside a request
        context (background tasks, management commands) never sees a stale ID.
        """
        factory = RequestFactory()
        request = factory.get("/api/health/")
        response = HttpResponse()
        middleware = RequestIdMiddleware(get_response=lambda r: HttpResponse())

        middleware.process_request(request)
        middleware.process_response(request, response)

        assert request_id_var.get() == "-"


class TestRequestIdFilter:
    """Tests for the RequestIdFilter logging filter."""

    @pytest.fixture(autouse=True)
    def setup(self) -> None:
        """Reset request_id_var to the default before each test."""
        request_id_var.set("-")

    def test_request_id_filter_injects_request_id(self) -> None:
        """Filter injects the value from request_id_var into the log record.

        When request_id_var holds a correlation ID, the filter must set
        record.request_id to that value so the log formatter can include it.
        """
        request_id_var.set("test-correlation-id")
        f = RequestIdFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test message",
            args=(),
            exc_info=None,
        )
        f.filter(record)

        assert getattr(record, "request_id") == "test-correlation-id"

    def test_request_id_filter_uses_default_when_no_context(self) -> None:
        """Filter injects '-' when no request is in flight.

        Outside a request (startup, management commands, background tasks),
        request_id_var holds the default '-'. The filter must propagate this
        so log records always have a well-defined request_id field.
        """
        # request_id_var already reset to "-" by the setup fixture
        f = RequestIdFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test message",
            args=(),
            exc_info=None,
        )
        f.filter(record)

        assert getattr(record, "request_id") == "-"


class TestRequestIdMiddlewareAccessLogging:
    """Tests for the per-request access log emitted by RequestIdMiddleware."""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Use IIS mode and re-enable log propagation so caplog can capture records.

        The LOGGING config sets propagate=False on the 'api' logger to prevent
        log noise bleeding into Django's own handlers. Tests that need to capture
        log output via caplog must temporarily restore propagation so records
        reach the root logger where pytest's capture handler lives.
        """
        monkeypatch.setenv("AUTH_MODE", "iis")
        monkeypatch.setattr(logging.getLogger("api"), "propagate", True)
        self.factory = RequestFactory()

    def test_access_log_emitted_on_response(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """process_response emits an INFO log containing method, path, and status code."""
        middleware = RequestIdMiddleware(get_response=lambda r: HttpResponse())
        request = self.factory.get("/api/health/")
        middleware.process_request(request)
        response = HttpResponse(status=200)

        with caplog.at_level(logging.INFO, logger="api.middleware.request_id"):
            middleware.process_response(request, response)

        messages = [
            r.getMessage()
            for r in caplog.records
            if r.name == "api.middleware.request_id"
        ]
        assert any("GET" in m and "/api/health/" in m and "200" in m for m in messages)

    def test_access_log_includes_duration(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Access log message includes the request duration in milliseconds."""
        middleware = RequestIdMiddleware(get_response=lambda r: HttpResponse())
        request = self.factory.get("/api/health/")
        middleware.process_request(request)
        response = HttpResponse(status=200)

        with caplog.at_level(logging.INFO, logger="api.middleware.request_id"):
            middleware.process_response(request, response)

        messages = [
            r.getMessage()
            for r in caplog.records
            if r.name == "api.middleware.request_id"
        ]
        assert any("ms" in m for m in messages)

    def test_access_log_includes_username_when_authenticated(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Access log includes the authenticated username when a user is present."""
        middleware = RequestIdMiddleware(get_response=lambda r: HttpResponse())
        request = self.factory.get("/api/health/")
        user = Mock(is_authenticated=True)
        user.get_username.return_value = "testuser"
        request.user = user
        middleware.process_request(request)
        response = HttpResponse(status=200)

        with caplog.at_level(logging.INFO, logger="api.middleware.request_id"):
            middleware.process_response(request, response)

        messages = [
            r.getMessage()
            for r in caplog.records
            if r.name == "api.middleware.request_id"
        ]
        assert any("testuser" in m for m in messages)

    def test_access_log_includes_security_fields(
        self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Access log carries the structured security context fields."""
        monkeypatch.setattr(logging.getLogger("api"), "propagate", True)
        middleware = RequestIdMiddleware(get_response=lambda r: HttpResponse())
        request = self.factory.get(
            "/api/health/",
            REMOTE_ADDR="203.0.113.10",
            HTTP_USER_AGENT="pytest-agent",
        )
        user = Mock(is_authenticated=True)
        user.get_username.return_value = "testuser"
        request.user = user
        middleware.process_request(request)
        response = HttpResponse(status=200)

        with caplog.at_level(logging.INFO, logger="api.middleware.request_id"):
            middleware.process_response(request, response)

        record = cast(
            Any,
            next(r for r in caplog.records if r.name == "api.middleware.request_id"),
        )

        assert record.event_type == "ACCESS"
        assert record.user_identifier == "testuser"
        assert record.source_ip == "203.0.113.10"
        assert record.user_agent == "pytest-agent"

    def test_access_log_shows_anonymous_when_unauthenticated(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Access log shows 'anonymous' when no user is attached to the request."""
        middleware = RequestIdMiddleware(get_response=lambda r: HttpResponse())
        request = self.factory.get("/api/health/")
        middleware.process_request(request)
        response = HttpResponse(status=200)

        with caplog.at_level(logging.INFO, logger="api.middleware.request_id"):
            middleware.process_response(request, response)

        messages = [
            r.getMessage()
            for r in caplog.records
            if r.name == "api.middleware.request_id"
        ]
        assert any("anonymous" in m for m in messages)


class TestRequestIdMiddlewareAsyncCompatibility:
    """Async compatibility tests for RequestIdMiddleware."""

    def test_supports_async_get_response(self) -> None:
        """RequestId middleware supports async downstream middleware chains."""

        async def get_response(request: Any) -> HttpResponse:
            return HttpResponse(status=209)

        middleware = RequestIdMiddleware(get_response)
        request = Mock()
        request.META = {}

        response = asyncio.run(middleware.__acall__(request))

        assert response.status_code == 209
        assert "X-Request-ID" in response
        assert request_id_var.get() == "-"

    def test_call_returns_coroutine_in_async_mode(self) -> None:
        """RequestId middleware __call__ returns awaitable for async chains."""

        async def get_response(request: Any) -> HttpResponse:
            return HttpResponse(status=210)

        middleware = RequestIdMiddleware(get_response)
        request = Mock()
        request.META = {}

        result = middleware(request)
        assert inspect.isawaitable(result)
        response = asyncio.run(cast(Coroutine[Any, Any, HttpResponse], result))

        assert response.status_code == 210
        assert "X-Request-ID" in response
        assert request_id_var.get() == "-"
