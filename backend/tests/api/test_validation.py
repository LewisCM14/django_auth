"""Tests for api.validation."""

from __future__ import annotations

from urllib.parse import urlparse

import pytest
from django.core.exceptions import ImproperlyConfigured

from api.validation import (
    _ensure_non_empty_string,
    _validate_url_port,
    validate_allowed_hosts,
    validate_api_version,
    validate_cors_allowed_origins,
    validate_distinguished_name,
    validate_hostname,
    validate_ldap_base_dn,
    validate_ldap_server_uri,
    validate_log_format,
    validate_log_level,
    validate_username,
)


class TestValidationHelpers:
    """Tests for the low-level validation helpers."""

    def test_ensure_non_empty_string_strips_whitespace(self) -> None:
        """Non-empty values are stripped before being returned."""
        assert _ensure_non_empty_string("  value  ", "FIELD") == "value"

    def test_ensure_non_empty_string_rejects_blank_value(self) -> None:
        """Blank values raise ImproperlyConfigured."""
        with pytest.raises(ImproperlyConfigured, match="FIELD must be"):
            _ensure_non_empty_string("", "FIELD")

    def test_validate_url_port_accepts_valid_port(self) -> None:
        """Valid URL ports pass through unchanged."""
        parsed = urlparse("https://example.com:443")

        _validate_url_port(parsed, "https://example.com:443", "FIELD")

    def test_validate_url_port_rejects_out_of_range_port(self) -> None:
        """Ports above 65535 are rejected."""
        parsed = urlparse("https://example.com:65536")

        with pytest.raises(ImproperlyConfigured, match="Port is out of range"):
            _validate_url_port(parsed, "https://example.com:65536", "FIELD")

    def test_validate_url_port_rejects_zero_port(self) -> None:
        """Port zero is rejected by the explicit range check."""
        parsed = urlparse("https://example.com:0")

        with pytest.raises(
            ImproperlyConfigured, match="Port must be between 1 and 65535"
        ):
            _validate_url_port(parsed, "https://example.com:0", "FIELD")


class TestHostnameValidation:
    """Tests for host and hostname allowlist validation."""

    @pytest.mark.parametrize(
        ("host", "expected"),
        [
            ("localhost", "localhost"),
            ("192.0.2.10", "192.0.2.10"),
            ("app.example.local", "app.example.local"),
        ],
    )
    def test_validate_hostname_accepts_allowed_values(
        self, host: str, expected: str
    ) -> None:
        """localhost, IPs, and valid hostnames are accepted."""
        assert validate_hostname(host) == expected

    def test_validate_hostname_rejects_invalid_value(self) -> None:
        """Malformed hostnames are rejected."""
        with pytest.raises(ImproperlyConfigured, match="Invalid host value"):
            validate_hostname("bad host!")

    def test_validate_allowed_hosts_parses_exact_allowlist(self) -> None:
        """Comma-separated allowed hosts are preserved in order."""
        assert validate_allowed_hosts("localhost,192.0.2.10,app.example.local") == [
            "localhost",
            "192.0.2.10",
            "app.example.local",
        ]

    def test_validate_allowed_hosts_rejects_empty_entry(self) -> None:
        """Empty allowlist entries fail closed."""
        with pytest.raises(ImproperlyConfigured, match="ALLOWED_HOSTS contains"):
            validate_allowed_hosts("localhost,,app.example.local")


class TestOriginValidation:
    """Tests for CORS origin validation."""

    def test_validate_cors_allowed_origins_allows_valid_origins(self) -> None:
        """Absolute http/https origins without paths are accepted."""
        assert validate_cors_allowed_origins(
            "https://portal.example.com:8443, http://localhost:3000"
        ) == ["https://portal.example.com:8443", "http://localhost:3000"]

    def test_validate_cors_allowed_origins_rejects_empty_entry(self) -> None:
        """Blank list entries fail closed."""
        with pytest.raises(ImproperlyConfigured, match="contains an empty entry"):
            validate_cors_allowed_origins("https://portal.example.com, ")

    @pytest.mark.parametrize(
        ("origin", "message"),
        [
            ("ftp://portal.example.com", "Expected an http or https origin"),
            ("https:///", "Missing host"),
            (
                "https://portal.example.com/path",
                "Paths, queries, and fragments are not allowed",
            ),
            ("https://user:pass@portal.example.com", "Userinfo is not allowed"),
        ],
    )
    def test_validate_cors_allowed_origins_rejects_invalid_origins(
        self, origin: str, message: str
    ) -> None:
        """Malformed origin formats are rejected."""
        with pytest.raises(ImproperlyConfigured, match=message):
            validate_cors_allowed_origins(origin)


class TestLdapValidation:
    """Tests for LDAP and distinguished-name validation."""

    def test_validate_ldap_server_uri_allows_valid_uri(self) -> None:
        """A valid ldap:// or ldaps:// URI passes validation."""
        assert validate_ldap_server_uri("ldaps://dc.example.com:636") == (
            "ldaps://dc.example.com:636"
        )

    @pytest.mark.parametrize(
        ("uri", "message"),
        [
            ("http://dc.example.com", "Expected ldap:// or ldaps://"),
            ("ldap:///", "A host is required"),
            (
                "ldap://dc.example.com/ou=users",
                "Paths, queries, and fragments are not allowed",
            ),
            ("ldap://user:pass@dc.example.com", "Userinfo is not allowed"),
        ],
    )
    def test_validate_ldap_server_uri_rejects_invalid_values(
        self, uri: str, message: str
    ) -> None:
        """Malformed LDAP server URIs are rejected."""
        with pytest.raises(ImproperlyConfigured, match=message):
            validate_ldap_server_uri(uri)

    def test_validate_ldap_base_dn_accepts_valid_dn(self) -> None:
        """A comma-separated DN passes validation."""
        assert validate_ldap_base_dn("DC=corp,DC=local") == "DC=corp,DC=local"

    def test_validate_ldap_base_dn_rejects_invalid_dn(self) -> None:
        """Malformed DNs fail closed."""
        with pytest.raises(ImproperlyConfigured, match="LDAP_BASE_DN"):
            validate_ldap_base_dn("not-a-dn")

    def test_validate_distinguished_name_accepts_valid_dn(self) -> None:
        """Active Directory DNs use the same strict format."""
        assert (
            validate_distinguished_name(
                "CN=Admins,OU=Groups,DC=corp,DC=local", field_name="ADMIN_AD_GROUP"
            )
            == "CN=Admins,OU=Groups,DC=corp,DC=local"
        )

    def test_validate_distinguished_name_rejects_invalid_dn(self) -> None:
        """Invalid distinguished names identify the field name in the error."""
        with pytest.raises(ImproperlyConfigured, match="ADMIN_AD_GROUP"):
            validate_distinguished_name("broken-value", field_name="ADMIN_AD_GROUP")


class TestUserAndVersionValidation:
    """Tests for username, version, and logging-related validation."""

    @pytest.mark.parametrize(
        "username",
        ["DOMAIN\\user-1", "corp.local\\alice"],
    )
    def test_validate_username_allows_domain_prefix(self, username: str) -> None:
        """REMOTE_USER values accept a domain prefix when allowed."""
        assert validate_username(username, allow_domain_prefix=True) == username

    def test_validate_username_rejects_invalid_domain_prefix(self) -> None:
        """Invalid REMOTE_USER values fail closed."""
        with pytest.raises(ImproperlyConfigured, match="REMOTE_USER value"):
            validate_username("DOMAIN\\bad/user", allow_domain_prefix=True)

    @pytest.mark.parametrize("username", ["alice", "bob.smith_1"])
    def test_validate_username_without_domain_prefix(self, username: str) -> None:
        """Plain usernames accept the allowed character set."""
        assert validate_username(username, allow_domain_prefix=False) == username

    def test_validate_username_rejects_plain_invalid_username(self) -> None:
        """Plain usernames reject invalid characters."""
        with pytest.raises(ImproperlyConfigured, match="Invalid username"):
            validate_username("alice/admin", allow_domain_prefix=False)

    def test_validate_api_version_accepts_build_label(self) -> None:
        """Version labels are preserved when they match the allowlist."""
        assert validate_api_version("v1.2.3") == "v1.2.3"

    def test_validate_api_version_rejects_invalid_label(self) -> None:
        """Malformed API versions fail closed."""
        with pytest.raises(ImproperlyConfigured, match="API_VERSION"):
            validate_api_version("-bad-version")

    @pytest.mark.parametrize(
        "value",
        ["json", "TEXT"],
    )
    def test_validate_log_format_accepts_known_values(self, value: str) -> None:
        """Log format names are normalized to lowercase."""
        assert validate_log_format(value) == value.lower()

    def test_validate_log_format_rejects_unknown_value(self) -> None:
        """Unsupported log formats fail closed."""
        with pytest.raises(ImproperlyConfigured, match="LOG_FORMAT"):
            validate_log_format("yaml")

    @pytest.mark.parametrize(
        "value",
        ["debug", "WARNING"],
    )
    def test_validate_log_level_accepts_known_values(self, value: str) -> None:
        """Log levels are normalized to uppercase."""
        assert validate_log_level(value) == value.upper()

    def test_validate_log_level_rejects_unknown_value(self) -> None:
        """Unsupported log levels fail closed."""
        with pytest.raises(ImproperlyConfigured, match="LOG_LEVEL"):
            validate_log_level("trace")
