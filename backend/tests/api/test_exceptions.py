"""Tests for the custom DRF exception handler (api/exceptions.py).

Verifies that every code path produces the standard error envelope shape:
    {"detail": "...", "request_id": "<uuid>"}

The handler is NOT yet wired into settings at this step — tests call it
directly so the tests remain fast and isolated.
"""

from __future__ import annotations

import json
import logging
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from django.test import RequestFactory
from rest_framework.exceptions import (
    AuthenticationFailed,
    NotFound,
    PermissionDenied,
    ValidationError,
)

from api.exceptions import api_exception_handler
from api.middleware.request_id import request_id_var


def _make_context(request_id: str = "test-req-id") -> dict:
    """Build a minimal DRF context dict with a mock request."""
    request: Any = RequestFactory().get(
        "/api/test/",
        REMOTE_ADDR="203.0.113.8",
        HTTP_USER_AGENT="pytest-agent",
    )
    request.request_id = request_id
    request.user = None
    return {"request": request, "view": MagicMock(), "args": [], "kwargs": {}}


class TestApiExceptionHandlerDrfExceptions:
    """Handler delegates DRF/Django exceptions and enriches with request_id."""

    def test_drf_api_exception_returns_detail_and_request_id(self) -> None:
        """NotFound (404) response contains both detail and request_id fields."""
        context = _make_context("abc-123")
        response = api_exception_handler(NotFound(), context)

        assert response is not None
        assert response.status_code == 404
        data = response.data  # type: ignore[union-attr]  # Response|JsonResponse union; JsonResponse has no .data
        assert "detail" in data
        assert data["request_id"] == "abc-123"

    def test_authentication_failed_returns_401_with_request_id(self) -> None:
        """AuthenticationFailed (401) response includes request_id."""
        context = _make_context("auth-req-id")
        response = api_exception_handler(AuthenticationFailed(), context)

        assert response is not None
        assert response.status_code == 401
        assert response.data["request_id"] == "auth-req-id"  # type: ignore[union-attr]  # Response|JsonResponse union; JsonResponse has no .data

    def test_permission_denied_returns_403_with_request_id(self) -> None:
        """PermissionDenied (403) response includes request_id."""
        context = _make_context("perm-req-id")
        response = api_exception_handler(PermissionDenied(), context)

        assert response is not None
        assert response.status_code == 403
        assert response.data["request_id"] == "perm-req-id"  # type: ignore[union-attr]  # Response|JsonResponse union; JsonResponse has no .data

    def test_validation_error_preserves_field_errors_and_adds_request_id(
        self,
    ) -> None:
        """ValidationError preserves field-level detail dict and adds request_id."""
        context = _make_context("val-req-id")
        exc = ValidationError({"username": ["This field is required."]})
        response = api_exception_handler(exc, context)

        assert response is not None
        assert response.status_code == 400
        data = response.data  # type: ignore[union-attr]  # Response|JsonResponse union; JsonResponse has no .data
        assert "username" in data
        assert data["request_id"] == "val-req-id"

    def test_validation_error_logs_input_validation_failure(
        self,
        caplog: pytest.LogCaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """ValidationError emits a structured security log for input validation failures."""
        monkeypatch.setattr(logging.getLogger("api"), "propagate", True)
        context = _make_context("val-log-id")

        with caplog.at_level(logging.WARNING, logger="api.exceptions"):
            api_exception_handler(
                ValidationError({"username": ["This field is required."]}), context
            )

        record = cast(
            Any, next(r for r in caplog.records if r.name == "api.exceptions")
        )
        assert record.event_type == "INPUT_VALIDATION_FAILURE"
        assert record.action_attempted == "validate request data"
        assert record.result == "failure"
        assert record.status_code == 400
        assert record.request_id == "val-log-id"


class TestApiExceptionHandlerUnhandled:
    """Handler catches unhandled exceptions, logs them, and returns safe 500."""

    def test_unhandled_exception_returns_500_with_request_id(self) -> None:
        """RuntimeError (unhandled) produces a 500 with the generic detail and request_id."""
        request_id_var.set("unhandled-req-id")
        context = _make_context("unhandled-req-id")
        response = api_exception_handler(RuntimeError("boom"), context)

        assert response is not None
        assert response.status_code == 500
        body = json.loads(response.content)
        assert body["detail"] == "An unexpected error occurred."
        assert body["request_id"] == "unhandled-req-id"

    def test_unhandled_exception_logs_traceback(
        self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """RuntimeError causes an ERROR log with exc_info (traceback) via logger.exception."""
        monkeypatch.setattr(logging.getLogger("api"), "propagate", True)
        context = _make_context("log-req-id")

        with caplog.at_level(logging.ERROR, logger="api.exceptions"):
            api_exception_handler(RuntimeError("something went wrong"), context)

        records = [cast(Any, r) for r in caplog.records if r.name == "api.exceptions"]
        assert len(records) == 1
        assert records[0].levelno == logging.ERROR
        assert records[0].exc_info is not None
        assert records[0].event_type == "UNHANDLED_EXCEPTION"
        assert records[0].exception_type == "RuntimeError"
        assert records[0].status_code == 500
        assert records[0].request_id == "log-req-id"
