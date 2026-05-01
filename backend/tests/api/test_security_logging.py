"""Tests for api.security_logging."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from api.security_logging import (
    _first_forwarded_for,
    _resolve_source_ip,
    build_security_event_fields,
)


def _make_user(
    username: object = "DOMAIN\\user", *, is_authenticated: bool = True
) -> Any:
    user = SimpleNamespace(is_authenticated=is_authenticated)

    def get_username() -> object:
        return username

    user.get_username = get_username
    return user


def _make_request(
    *,
    request_id: str = "req-123",
    path: str = "/api/user/",
    meta: dict[str, object] | None = None,
    user: Any | None = None,
) -> Any:
    return SimpleNamespace(
        request_id=request_id,
        path=path,
        META=meta
        if meta is not None
        else {
            "REMOTE_ADDR": "203.0.113.10",
            "HTTP_USER_AGENT": "pytest-agent",
        },
        user=user if user is not None else _make_user(),
    )


class TestBuildSecurityEventFields:
    """Tests for the structured security-event payload builder."""

    def test_build_security_event_fields_uses_request_context(self) -> None:
        """Request metadata is copied into the emitted payload."""
        request = _make_request()

        payload = build_security_event_fields(
            request,
            event_type="AUTHENTICATION_SUCCESS",
            action_attempted="authenticate REMOTE_USER",
            result="failure",
            status_code=403,
            duration_ms=12.345,
            exception_type="PermissionDenied",
            resource_accessed="/api/user/",
            extra_note="kept",
        )

        assert payload["request_id"] == "req-123"
        assert payload["event_type"] == "AUTHENTICATION_SUCCESS"
        assert payload["user_identifier"] == "DOMAIN\\user"
        assert payload["source_ip"] == "203.0.113.10"
        assert payload["user_agent"] == "pytest-agent"
        assert payload["action_attempted"] == "authenticate REMOTE_USER"
        assert payload["result"] == "failure"
        assert payload["resource_accessed"] == "/api/user/"
        assert payload["error_id"] == "req-123"
        assert payload["status_code"] == 403
        assert payload["duration_ms"] == 12.3
        assert payload["exception_type"] == "PermissionDenied"
        assert payload["extra_note"] == "kept"

    def test_build_security_event_fields_handles_missing_request(self) -> None:
        """Missing request context falls back to safe sentinel values."""
        payload = build_security_event_fields(
            None,
            event_type="UNHANDLED_EXCEPTION",
            action_attempted="execute request",
            result="success",
        )
        explicit_payload = build_security_event_fields(
            None,
            event_type="UNHANDLED_EXCEPTION",
            action_attempted="execute request",
            result="success",
            request_id="override",
            error_id="explicit-error",
        )

        assert payload["request_id"] == "-"
        assert payload["user_identifier"] == "anonymous"
        assert payload["source_ip"] == "-"
        assert payload["user_agent"] == "-"
        assert payload["resource_accessed"] == "-"
        assert explicit_payload["request_id"] == "override"
        assert explicit_payload["error_id"] == "explicit-error"

    def test_build_security_event_fields_handles_non_string_username(self) -> None:
        """Non-string usernames fall back to anonymous."""
        request = _make_request(user=_make_user(123))

        payload = build_security_event_fields(
            request,
            event_type="AUTHENTICATION_SUCCESS",
            action_attempted="authenticate REMOTE_USER",
            result="success",
        )

        assert payload["user_identifier"] == "anonymous"


class TestSecurityLoggingHelpers:
    """Tests for the internal helper functions."""

    def test_resolve_source_ip_prefers_remote_addr_when_hop_not_trusted(self) -> None:
        """Forwarded-for is ignored unless the immediate hop is trusted."""
        request = _make_request(
            meta={
                "HTTP_X_FORWARDED_FOR": "198.51.100.1, 203.0.113.10",
                "REMOTE_ADDR": "203.0.113.10",
                "HTTP_USER_AGENT": "pytest-agent",
            }
        )

        assert _resolve_source_ip(request) == "203.0.113.10"

    def test_resolve_source_ip_uses_forwarded_for_from_loopback_hop(self) -> None:
        """Forwarded-for is trusted when the request is proxied from loopback."""
        request = _make_request(
            meta={
                "HTTP_X_FORWARDED_FOR": "198.51.100.1, 127.0.0.1",
                "REMOTE_ADDR": "127.0.0.1",
                "HTTP_USER_AGENT": "pytest-agent",
            }
        )

        assert _resolve_source_ip(request) == "198.51.100.1"

    def test_resolve_source_ip_returns_sentinel_for_invalid_ip(self) -> None:
        """Malformed IP addresses fall back to the sentinel value."""
        request = _make_request(
            meta={
                "REMOTE_ADDR": "999.999.999.999",
                "HTTP_USER_AGENT": "pytest-agent",
            }
        )

        assert _resolve_source_ip(request) == "-"

    @pytest.mark.parametrize(
        "value, expected",
        [
            ("198.51.100.1, 203.0.113.10", "198.51.100.1"),
            (" 198.51.100.1 ", "198.51.100.1"),
            ("", None),
            (None, None),
        ],
    )
    def test_first_forwarded_for_handles_values(
        self, value: object, expected: str | None
    ) -> None:
        """Forwarded-for parsing returns the first IP or None."""
        assert _first_forwarded_for(value) == expected
