"""Shared fixtures and configuration for all tests.

Pytest configuration, shared fixtures, and test utilities are defined here.
These fixtures are automatically available to all test files.
"""

from __future__ import annotations

import pytest
from django.test import Client

from api.constants import ADMIN_AD_GROUP, VIEWER_AD_GROUP


@pytest.fixture
def admin_client(monkeypatch: pytest.MonkeyPatch) -> Client:
    """Client representing an authenticated admin user.

    The authorization LDAP lookup is mocked so this identity resolves to
    the ``app_admin`` role.
    """

    def mock_query_ldap_groups(username: str) -> list[str]:
        """Return mocked AD groups for known test identities."""
        if username == "DOMAIN\\admin_user":
            return [ADMIN_AD_GROUP]
        return []

    monkeypatch.setattr(
        "api.middleware.authorization.query_ldap_groups",
        mock_query_ldap_groups,
    )
    monkeypatch.setattr(
        "api.middleware.authentication.WindowsAuthIdentityResolver.resolve",
        lambda _self, _token: "DOMAIN\\admin_user",
    )
    monkeypatch.setenv("AUTH_MODE", "iis")
    monkeypatch.setenv("TRUSTED_AUTH_PROXY_IPS", "127.0.0.1")

    client = Client()
    client.defaults["HTTP_X_IIS_WINDOWSAUTHTOKEN"] = "0xA11"
    client.defaults["REMOTE_ADDR"] = "127.0.0.1"
    return client


@pytest.fixture
def viewer_client(monkeypatch: pytest.MonkeyPatch) -> Client:
    """Client representing an authenticated viewer user."""

    def mock_query_ldap_groups(username: str) -> list[str]:
        """Return mocked AD groups for known test identities."""
        if username == "DOMAIN\\viewer_user":
            return [VIEWER_AD_GROUP]
        return []

    monkeypatch.setattr(
        "api.middleware.authorization.query_ldap_groups",
        mock_query_ldap_groups,
    )
    monkeypatch.setattr(
        "api.middleware.authentication.WindowsAuthIdentityResolver.resolve",
        lambda _self, _token: "DOMAIN\\viewer_user",
    )
    monkeypatch.setenv("AUTH_MODE", "iis")
    monkeypatch.setenv("TRUSTED_AUTH_PROXY_IPS", "127.0.0.1")

    client = Client()
    client.defaults["HTTP_X_IIS_WINDOWSAUTHTOKEN"] = "0xB22"
    client.defaults["REMOTE_ADDR"] = "127.0.0.1"
    return client


@pytest.fixture
def unauthenticated_client(monkeypatch: pytest.MonkeyPatch) -> Client:
    """Client with no authenticated IIS Windows auth token identity."""
    monkeypatch.setenv("AUTH_MODE", "iis")
    monkeypatch.setenv("TRUSTED_AUTH_PROXY_IPS", "127.0.0.1")
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
    monkeypatch.setattr(
        "api.middleware.authentication.WindowsAuthIdentityResolver.resolve",
        lambda _self, _token: "DOMAIN\\unauthorized_user",
    )
    monkeypatch.setenv("AUTH_MODE", "iis")
    monkeypatch.setenv("TRUSTED_AUTH_PROXY_IPS", "127.0.0.1")

    client = Client()
    client.defaults["HTTP_X_IIS_WINDOWSAUTHTOKEN"] = "0xC33"
    client.defaults["REMOTE_ADDR"] = "127.0.0.1"
    return client
