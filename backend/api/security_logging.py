"""Structured security event helpers.

These helpers normalize the security-relevant metadata that we want to emit
from authentication, authorization, throttling, and exception handling code.
The formatter turns the resulting log record extras into JSON fields.
"""

from __future__ import annotations

import ipaddress
from typing import Any

from django.http import HttpRequest

from api.request_user import get_request_user

SECURITY_EXTRA_FIELDS: tuple[str, ...] = (
    "event_type",
    "user_identifier",
    "source_ip",
    "user_agent",
    "action_attempted",
    "result",
    "resource_accessed",
    "error_id",
    "status_code",
    "duration_ms",
    "exception_type",
)


def build_security_event_fields(
    request: HttpRequest | None = None,
    *,
    event_type: str,
    action_attempted: str,
    result: str,
    resource_accessed: str | None = None,
    user_identifier: str | None = None,
    source_ip: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
    error_id: str | None = None,
    status_code: int | None = None,
    duration_ms: float | None = None,
    **extra_fields: Any,
) -> dict[str, Any]:
    """Build structured JSON-friendly fields for a security log record."""

    payload: dict[str, Any] = {
        "request_id": _resolve_request_id(request, request_id),
        "event_type": event_type,
        "user_identifier": _resolve_user_identifier(request, user_identifier),
        "source_ip": source_ip
        if source_ip is not None
        else _resolve_source_ip(request),
        "user_agent": user_agent
        if user_agent is not None
        else _resolve_user_agent(request),
        "action_attempted": action_attempted,
        "result": result,
        "resource_accessed": resource_accessed
        if resource_accessed is not None
        else _resolve_resource_accessed(request),
    }

    if error_id is not None:
        payload["error_id"] = error_id
    elif result == "failure":
        payload["error_id"] = payload["request_id"]

    if status_code is not None:
        payload["status_code"] = status_code
    if duration_ms is not None:
        payload["duration_ms"] = round(duration_ms, 1)

    for key, value in extra_fields.items():
        if value is not None:
            payload[key] = value

    return payload


def _resolve_request_id(request: HttpRequest | None, request_id: str | None) -> str:
    if isinstance(request_id, str) and request_id:
        return request_id
    if request is None:
        return "-"

    request_dict = getattr(request, "__dict__", {})
    candidate = request_dict.get("request_id")
    return candidate if isinstance(candidate, str) and candidate else "-"


def _resolve_user_identifier(
    request: HttpRequest | None, user_identifier: str | None
) -> str:
    if isinstance(user_identifier, str) and user_identifier:
        return user_identifier
    if request is None:
        return "anonymous"

    user = get_request_user(request)
    if user is None or not getattr(user, "is_authenticated", False):
        return "anonymous"

    username = user.get_username()
    return username if isinstance(username, str) and username else "anonymous"


def _resolve_source_ip(request: HttpRequest | None) -> str:
    if request is None:
        return "-"

    request_meta = getattr(request, "__dict__", {}).get("META") or {}
    remote_ip = _parse_ip(request_meta.get("REMOTE_ADDR"))
    if remote_ip is None:
        return "-"

    # Only trust X-Forwarded-For when the immediate hop is local IIS.
    if remote_ip.is_loopback:
        forwarded_ip = _parse_ip(
            _first_forwarded_for(request_meta.get("HTTP_X_FORWARDED_FOR"))
        )
        if forwarded_ip is not None:
            return str(forwarded_ip)

    return str(remote_ip)


def _resolve_user_agent(request: HttpRequest | None) -> str:
    if request is None:
        return "-"

    request_meta = getattr(request, "__dict__", {}).get("META") or {}
    candidate = request_meta.get("HTTP_USER_AGENT")
    if not isinstance(candidate, str) or not candidate.strip():
        return "-"
    return candidate.strip()[:512]


def _resolve_resource_accessed(request: HttpRequest | None) -> str:
    if request is None:
        return "-"

    request_dict = getattr(request, "__dict__", {})
    candidate = request_dict.get("path")
    if isinstance(candidate, str) and candidate:
        return candidate
    return "-"


def _first_forwarded_for(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    first_value = value.split(",", 1)[0].strip()
    return first_value or None


def _parse_ip(value: object) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return ipaddress.ip_address(value.strip())
    except ValueError:
        return None
