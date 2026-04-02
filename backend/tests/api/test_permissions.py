"""Tests for per-view authorization permissions."""

from __future__ import annotations

from api.permissions import (
    AUTHZ_POLICY_ATTR,
    AUTHZ_ROLES_ATTR,
    authz_authenticated,
    authz_public,
    authz_roles,
)


def test_authz_public_sets_public_policy() -> None:
    """authz_public marks a view as public."""

    def sample_view() -> None:
        return None

    decorated = authz_public(sample_view)
    assert decorated is sample_view
    assert getattr(sample_view, AUTHZ_POLICY_ATTR) == "public"


def test_authz_authenticated_sets_authenticated_policy() -> None:
    """authz_authenticated marks a view as requiring IIS authentication only."""

    def sample_view() -> None:
        return None

    decorated = authz_authenticated(sample_view)
    assert decorated is sample_view
    assert getattr(sample_view, AUTHZ_POLICY_ATTR) == "authenticated"


def test_authz_roles_sets_policy_and_roles() -> None:
    """authz_roles stores policy and required roles metadata."""

    def sample_view() -> None:
        return None

    decorated = authz_roles("app_admin", "app_viewer")(sample_view)
    assert decorated is sample_view
    assert getattr(sample_view, AUTHZ_POLICY_ATTR) == "roles"
    assert getattr(sample_view, AUTHZ_ROLES_ATTR) == ("app_admin", "app_viewer")
