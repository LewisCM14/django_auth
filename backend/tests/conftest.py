"""Shared fixtures and configuration for all tests.

Pytest configuration, shared fixtures, and test utilities are defined here.
These fixtures are automatically available to all test files.
"""

from __future__ import annotations

import pytest
from django.test import Client


@pytest.fixture
def admin_client(monkeypatch: pytest.MonkeyPatch) -> Client:
    """Client representing an authenticated admin user.

    The authorization LDAP lookup is mocked so this identity resolves to
    the ``app_admin`` role.
    """

    def mock_query_ldap_groups(username: str) -> list[str]:
        """Return mocked AD groups for known test identities."""
        if username == "DOMAIN\\admin_user":
            return ["CN=app-admins,OU=Groups,DC=corp,DC=local"]
        return []

    monkeypatch.setattr(
        "api.middleware.authorization.query_ldap_groups",
        mock_query_ldap_groups,
    )
    monkeypatch.setenv("AUTH_MODE", "iis")

    client = Client()
    client.defaults["HTTP_REMOTE_USER"] = "DOMAIN\\admin_user"
    return client


@pytest.fixture
def viewer_client(monkeypatch: pytest.MonkeyPatch) -> Client:
    """Client representing an authenticated viewer user."""

    def mock_query_ldap_groups(username: str) -> list[str]:
        """Return mocked AD groups for known test identities."""
        if username == "DOMAIN\\viewer_user":
            return ["CN=app-viewers,OU=Groups,DC=corp,DC=local"]
        return []

    monkeypatch.setattr(
        "api.middleware.authorization.query_ldap_groups",
        mock_query_ldap_groups,
    )
    monkeypatch.setenv("AUTH_MODE", "iis")

    client = Client()
    client.defaults["HTTP_REMOTE_USER"] = "DOMAIN\\viewer_user"
    return client


@pytest.fixture
def unauthenticated_client(monkeypatch: pytest.MonkeyPatch) -> Client:
    """Client with no authenticated REMOTE_USER identity."""
    # Explicitly exercise IIS-mode unauthenticated behavior.
    monkeypatch.setenv("AUTH_MODE", "iis")
    return Client()


@pytest.fixture
def unauthorized_client(monkeypatch: pytest.MonkeyPatch) -> Client:
    """Client with an identity that resolves to no application roles."""

    def mock_query_ldap_groups(username: str) -> list[str]:
        """Return no matching AD groups for any user."""
        return []

    monkeypatch.setattr(
        "api.middleware.authorization.query_ldap_groups",
        mock_query_ldap_groups,
    )
    monkeypatch.setenv("AUTH_MODE", "iis")

    client = Client()
    client.defaults["HTTP_REMOTE_USER"] = "DOMAIN\\unauthorized_user"
    return client
