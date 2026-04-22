"""Strict input validation helpers.

These helpers reject malformed configuration and request input rather than
attempting to normalize it.
"""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse

from django.core.exceptions import ImproperlyConfigured

_HOST_LABEL = r"(?!-)[A-Za-z0-9-]{1,63}(?<!-)"
_HOSTNAME_RE = re.compile(
    rf"^(?:localhost|{_HOST_LABEL}(?:\.{_HOST_LABEL})*)$",
    re.IGNORECASE,
)
_USERNAME_BODY = r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}"
_USERNAME_RE = re.compile(rf"^{_USERNAME_BODY}$")
_DOMAIN_BODY = rf"{_HOST_LABEL}(?:\.{_HOST_LABEL})*"
_REMOTE_USER_RE = re.compile(
    rf"^(?:(?P<domain>{_DOMAIN_BODY})\\)?(?P<user>{_USERNAME_BODY})$"
)
_LDAP_DN_RE = re.compile(
    r"^[A-Za-z][A-Za-z0-9-]*=[A-Za-z0-9 ._/-]+(?:,[A-Za-z][A-Za-z0-9-]*=[A-Za-z0-9 ._/-]+)*$"
)
_API_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")
_LOG_FORMATS = {"json", "text"}
_LOG_LEVELS = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}


def _ensure_non_empty_string(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ImproperlyConfigured(f"{field_name} must be a non-empty string.")
    return value.strip()


def _validate_url_port(parsed: object, raw_value: str, field_name: str) -> None:
    try:
        port = parsed.port  # type: ignore[attr-defined]  # urlparse() returns ParseResult; port is available at runtime but not on the narrow object type here.
    except ValueError as exc:
        raise ImproperlyConfigured(
            f"Invalid {field_name} '{raw_value}'. Port is out of range."
        ) from exc

    if port is not None and not (1 <= port <= 65535):
        raise ImproperlyConfigured(
            f"Invalid {field_name} '{raw_value}'. Port must be between 1 and 65535."
        )


def validate_hostname(host: str) -> str:
    """Validate a hostname or IP literal used in host allowlists."""

    candidate = _ensure_non_empty_string(host, "Host")
    if candidate == "localhost":
        return candidate

    try:
        ipaddress.ip_address(candidate)
        return candidate
    except ValueError:
        pass

    if _HOSTNAME_RE.fullmatch(candidate):
        return candidate

    raise ImproperlyConfigured(
        f"Invalid host value '{host}'. Expected localhost, an IP address, or a hostname."
    )


def validate_allowed_hosts(raw_value: str) -> list[str]:
    """Parse and validate ``ALLOWED_HOSTS`` as an exact allowlist."""

    if not raw_value.strip():
        return []

    hosts: list[str] = []
    for item in raw_value.split(","):
        host = item.strip()
        if not host:
            raise ImproperlyConfigured(
                "ALLOWED_HOSTS contains an empty entry. Provide only explicit hosts."
            )
        hosts.append(validate_hostname(host))

    return hosts


def validate_cors_allowed_origins(raw_value: str) -> list[str]:
    """Parse and validate ``CORS_ALLOWED_ORIGINS`` as exact origins."""

    if not raw_value.strip():
        return []

    origins: list[str] = []
    for item in raw_value.split(","):
        origin = item.strip()
        if not origin:
            raise ImproperlyConfigured(
                "CORS_ALLOWED_ORIGINS contains an empty entry. Provide only explicit origins."
            )

        parsed = urlparse(origin)
        if parsed.scheme not in {"http", "https"}:
            raise ImproperlyConfigured(
                f"Invalid CORS_ALLOWED_ORIGINS entry '{origin}'. Expected an http or https origin."
            )
        if not parsed.hostname:
            raise ImproperlyConfigured(
                f"Invalid CORS_ALLOWED_ORIGINS entry '{origin}'. Missing host."
            )
        if (
            parsed.path not in {"", "/"}
            or parsed.params
            or parsed.query
            or parsed.fragment
        ):
            raise ImproperlyConfigured(
                f"Invalid CORS_ALLOWED_ORIGINS entry '{origin}'. Paths, queries, and fragments are not allowed."
            )
        if parsed.username or parsed.password:
            raise ImproperlyConfigured(
                f"Invalid CORS_ALLOWED_ORIGINS entry '{origin}'. Userinfo is not allowed."
            )

        validate_hostname(parsed.hostname)
        _validate_url_port(parsed, origin, "CORS_ALLOWED_ORIGINS")
        origins.append(origin)

    return origins


def validate_ldap_server_uri(uri: str) -> str:
    """Validate the LDAP/LDAPS server URI used for Active Directory lookups."""

    candidate = _ensure_non_empty_string(uri, "LDAP_SERVER_URI")
    parsed = urlparse(candidate)
    if parsed.scheme not in {"ldap", "ldaps"}:
        raise ImproperlyConfigured(
            f"Invalid LDAP_SERVER_URI '{uri}'. Expected ldap:// or ldaps://."
        )
    if not parsed.hostname:
        raise ImproperlyConfigured(
            f"Invalid LDAP_SERVER_URI '{uri}'. A host is required."
        )
    if parsed.path not in {"", "/"} or parsed.params or parsed.query or parsed.fragment:
        raise ImproperlyConfigured(
            f"Invalid LDAP_SERVER_URI '{uri}'. Paths, queries, and fragments are not allowed."
        )
    if parsed.username or parsed.password:
        raise ImproperlyConfigured(
            f"Invalid LDAP_SERVER_URI '{uri}'. Userinfo is not allowed."
        )

    validate_hostname(parsed.hostname)
    _validate_url_port(parsed, uri, "LDAP_SERVER_URI")
    return candidate


def validate_ldap_base_dn(base_dn: str) -> str:
    """Validate a distinguished name used as the LDAP base DN."""

    candidate = _ensure_non_empty_string(base_dn, "LDAP_BASE_DN")
    if not _LDAP_DN_RE.fullmatch(candidate):
        raise ImproperlyConfigured(
            f"Invalid LDAP_BASE_DN '{base_dn}'. Expected a comma-separated DN of attr=value pairs."
        )
    return candidate


def validate_distinguished_name(value: str, *, field_name: str) -> str:
    """Validate an Active Directory distinguished name."""

    candidate = _ensure_non_empty_string(value, field_name)
    if not _LDAP_DN_RE.fullmatch(candidate):
        raise ImproperlyConfigured(
            f"Invalid {field_name} '{value}'. Expected a comma-separated DN of attr=value pairs."
        )
    return candidate


def validate_username(value: str, *, allow_domain_prefix: bool) -> str:
    """Validate a username or REMOTE_USER value with a strict allowlist."""

    candidate = _ensure_non_empty_string(value, "Username")
    if allow_domain_prefix:
        if _REMOTE_USER_RE.fullmatch(candidate):
            return candidate
        raise ImproperlyConfigured(
            f"Invalid REMOTE_USER value '{value}'. Expected DOMAIN\\username or username with allowed characters only."
        )

    if _USERNAME_RE.fullmatch(candidate):
        return candidate

    raise ImproperlyConfigured(
        f"Invalid username '{value}'. Expected 1-64 characters from [A-Za-z0-9._-]."
    )


def validate_api_version(value: str) -> str:
    """Validate the API version label surfaced to clients."""

    candidate = _ensure_non_empty_string(value, "API_VERSION")
    if not _API_VERSION_RE.fullmatch(candidate):
        raise ImproperlyConfigured(
            f"Invalid API_VERSION '{value}'. Expected a build label or SemVer-like token."
        )
    return candidate


def validate_log_format(value: str) -> str:
    """Validate the configured log format."""

    candidate = _ensure_non_empty_string(value, "LOG_FORMAT").lower()
    if candidate not in _LOG_FORMATS:
        raise ImproperlyConfigured("LOG_FORMAT must be either 'json' or 'text'.")
    return candidate


def validate_log_level(value: str) -> str:
    """Validate the configured Python logging level."""

    candidate = _ensure_non_empty_string(value, "LOG_LEVEL").upper()
    if candidate not in _LOG_LEVELS:
        raise ImproperlyConfigured(
            "LOG_LEVEL must be one of DEBUG, INFO, WARNING, ERROR, or CRITICAL."
        )
    return candidate
