"""Tests for the authorization middleware.

The authorization middleware enforces explicit per-view authorization via
decorators. Every view must declare ``@authz_public``, ``@authz_authenticated``,
or ``@authz_roles(...)``. There are no default permissions — future developers
must explicitly set authorization at the view level.

Role resolution happens only when a view requires roles:
- Dev mode: reads ``DEV_USER_ROLE`` environment variable
- IIS mode: queries LDAP (with caching) for AD group membership
"""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock, patch

import pytest
from django.core.cache import cache
from django.test import override_settings

from api.constants import ROLE_ADMIN, ROLE_VIEWER
from api.middleware.authorization import AuthorizationMiddleware


def _make_roles_view(
    roles: tuple[str, ...] = (ROLE_ADMIN, ROLE_VIEWER),
) -> Any:
    """Create a dummy view with roles policy for testing."""

    class RolesView:
        authz_policy = "roles"
        authz_roles = roles

    RolesView.__module__ = "api.views.sample"

    def wrapped_view() -> None:
        return None

    # Django's URL resolver attaches `view_class` dynamically to the callable
    # returned by `as_view()`. In tests we emulate that runtime shape.
    wrapped_view.view_class = RolesView  # type: ignore[attr-defined]
    return wrapped_view


class TestAuthorizationMiddlewareDevMode:
    """Tests for authorization middleware in dev mode (AUTH_MODE=dev)."""

    @staticmethod
    def get_response(request: Any) -> Mock:
        """Mock WSGI application for middleware testing."""
        response = Mock()
        response.status_code = 200
        return response

    def setup_method(self) -> None:
        """Clear cache before each test."""
        cache.clear()

    @override_settings(DEBUG=True)
    def test_dev_mode_assigns_admin_role_from_env(self) -> None:
        """In dev mode with DEV_USER_ROLE=admin, user gets app_admin role."""
        middleware = AuthorizationMiddleware(self.get_response)
        request = Mock()
        request.user = Mock(username="dev_admin")
        view_func = _make_roles_view()

        with patch.dict("os.environ", {"AUTH_MODE": "dev", "DEV_USER_ROLE": "admin"}):
            result = middleware.process_view(request, view_func, [], {})

        assert result is None
        assert ROLE_ADMIN in request.user.roles

    @override_settings(DEBUG=True)
    def test_dev_mode_defaults_to_admin(self) -> None:
        """When DEV_USER_ROLE is not set, defaults to admin."""
        middleware = AuthorizationMiddleware(self.get_response)
        request = Mock()
        request.user = Mock(username="dev_admin")
        view_func = _make_roles_view()

        with patch.dict("os.environ", {"AUTH_MODE": "dev"}, clear=False):
            result = middleware.process_view(request, view_func, [], {})

        assert result is None
        assert ROLE_ADMIN in request.user.roles

    @override_settings(DEBUG=True)
    def test_dev_mode_viewer_role_from_env(self) -> None:
        """In dev mode with DEV_USER_ROLE=viewer, user gets app_viewer role."""
        middleware = AuthorizationMiddleware(self.get_response)
        request = Mock()
        request.user = Mock(username="dev_viewer")
        view_func = _make_roles_view()

        with patch.dict("os.environ", {"AUTH_MODE": "dev", "DEV_USER_ROLE": "viewer"}):
            result = middleware.process_view(request, view_func, [], {})

        assert result is None
        assert request.user.roles == [ROLE_VIEWER]


class TestAuthorizationMiddlewareIISMode:
    """Tests for authorization middleware in IIS mode (AUTH_MODE=iis)."""

    @staticmethod
    def get_response(request: Any) -> Mock:
        """Mock WSGI application for middleware testing."""
        response = Mock()
        response.status_code = 200
        return response

    def setup_method(self) -> None:
        """Clear cache before each test."""
        cache.clear()

    @override_settings(DEBUG=False)
    def test_user_with_admin_group_gets_admin_role(self) -> None:
        """User in LDAP admin group receives app_admin role."""
        middleware = AuthorizationMiddleware(self.get_response)
        request = Mock()
        request.user = Mock(username="DOMAIN\\admin_user")
        view_func = _make_roles_view()

        with patch("api.middleware.authorization.query_ldap_groups") as mock_ldap:
            mock_ldap.return_value = ["CN=app-admins,OU=Groups,DC=corp,DC=local"]
            with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
                result = middleware.process_view(request, view_func, [], {})

        assert result is None
        assert ROLE_ADMIN in request.user.roles

    @override_settings(DEBUG=False)
    def test_user_with_viewer_group_gets_viewer_role(self) -> None:
        """User in LDAP viewer group receives app_viewer role."""
        middleware = AuthorizationMiddleware(self.get_response)
        request = Mock()
        request.user = Mock(username="DOMAIN\\viewer_user")
        view_func = _make_roles_view()

        with patch("api.middleware.authorization.query_ldap_groups") as mock_ldap:
            mock_ldap.return_value = ["CN=app-viewers,OU=Groups,DC=corp,DC=local"]
            with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
                result = middleware.process_view(request, view_func, [], {})

        assert result is None
        assert ROLE_VIEWER in request.user.roles

    @override_settings(DEBUG=False)
    def test_user_with_multiple_groups_gets_multiple_roles(self) -> None:
        """User in multiple AD groups gets all corresponding roles."""
        middleware = AuthorizationMiddleware(self.get_response)
        request = Mock()
        request.user = Mock(username="DOMAIN\\power_user")
        view_func = _make_roles_view()

        with patch("api.middleware.authorization.query_ldap_groups") as mock_ldap:
            mock_ldap.return_value = [
                "CN=app-admins,OU=Groups,DC=corp,DC=local",
                "CN=app-viewers,OU=Groups,DC=corp,DC=local",
            ]
            with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
                result = middleware.process_view(request, view_func, [], {})

        assert result is None
        assert ROLE_ADMIN in request.user.roles
        assert ROLE_VIEWER in request.user.roles

    @override_settings(DEBUG=False)
    def test_user_with_no_matching_groups_returns_403(self) -> None:
        """User authenticated but not in any configured AD group gets 403 JSON."""
        middleware = AuthorizationMiddleware(self.get_response)
        request = Mock()
        request.user = Mock(username="DOMAIN\\regular_user")
        view_func = _make_roles_view()

        with patch("api.middleware.authorization.query_ldap_groups") as mock_ldap:
            mock_ldap.return_value = ["CN=other-group,OU=Groups,DC=corp,DC=local"]
            with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
                result = middleware.process_view(request, view_func, [], {})

        assert result is not None
        assert result.status_code == 403
        import json

        body = json.loads(result.content)
        assert body == {"detail": "You do not have permission to perform this action."}

    @override_settings(DEBUG=False)
    def test_unauthenticated_request_returns_401(self) -> None:
        """Request without user identity returns 401 JSON response."""
        middleware = AuthorizationMiddleware(self.get_response)
        request = Mock()
        request.user = None
        view_func = _make_roles_view()

        with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
            result = middleware.process_view(request, view_func, [], {})

        assert result is not None
        assert result.status_code == 401

    @override_settings(DEBUG=False)
    def test_ldap_result_is_cached(self) -> None:
        """LDAP query result for a user is cached across requests."""
        middleware = AuthorizationMiddleware(self.get_response)
        view_func = _make_roles_view()

        with patch("api.middleware.authorization.query_ldap_groups") as mock_ldap:
            mock_ldap.return_value = ["CN=app-admins,OU=Groups,DC=corp,DC=local"]

            with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
                request1 = Mock()
                request1.user = Mock(username="DOMAIN\\cached_user")
                middleware.process_view(request1, view_func, [], {})
                assert mock_ldap.call_count == 1

                request2 = Mock()
                request2.user = Mock(username="DOMAIN\\cached_user")
                middleware.process_view(request2, view_func, [], {})
                assert mock_ldap.call_count == 1

    @override_settings(DEBUG=False)
    def test_cache_respects_ttl(self) -> None:
        """Cache expires after LDAP_CACHE_TTL; next request queries LDAP."""
        middleware = AuthorizationMiddleware(self.get_response)
        view_func = _make_roles_view()
        username = "DOMAIN\\ttl_user"

        with patch("api.middleware.authorization.query_ldap_groups") as mock_ldap:
            mock_ldap.return_value = ["CN=app-admins,OU=Groups,DC=corp,DC=local"]

            with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
                request1 = Mock()
                request1.user = Mock(username=username)
                middleware.process_view(request1, view_func, [], {})
                assert mock_ldap.call_count == 1

                cache.delete(f"ldap_groups_{username}")

                request2 = Mock()
                request2.user = Mock(username=username)
                middleware.process_view(request2, view_func, [], {})
                assert mock_ldap.call_count == 2

    @override_settings(DEBUG=False)
    def test_public_policy_bypasses_authorization(self) -> None:
        """Public policy views bypass all authorization checks."""
        middleware = AuthorizationMiddleware(self.get_response)
        request = Mock()
        request.user = None

        class PublicView:
            """Dummy class-based view marker for public policy."""

            authz_policy = "public"

        PublicView.__module__ = "api.views.health"

        def wrapped_view() -> None:
            """Dummy resolved callable used by Django for class-based views."""
            return None

        # Django's URL resolver attaches `view_class` dynamically to the callable
        # returned by `as_view()`. In tests we emulate that runtime shape.
        wrapped_view.view_class = PublicView  # type: ignore[attr-defined]

        with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
            result = middleware.process_view(request, wrapped_view, [], {})

        assert result is None

    @override_settings(DEBUG=False)
    def test_non_project_view_raises_improperly_configured(self) -> None:
        """Strict mode requires all routed views to live under api.views."""
        middleware = AuthorizationMiddleware(self.get_response)
        request = Mock()
        request.user = None

        def wrapped_view() -> None:
            """Dummy resolved callable for third-party view simulation."""
            return None

        wrapped_view.__module__ = "third_party.module"

        from django.core.exceptions import ImproperlyConfigured

        with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
            with pytest.raises(ImproperlyConfigured):
                middleware.process_view(request, wrapped_view, [], {})

    @override_settings(DEBUG=False)
    def test_authenticated_policy_allows_authenticated_user(self) -> None:
        """authz_authenticated policy allows access with identity only (no roles)."""
        middleware = AuthorizationMiddleware(self.get_response)
        request = Mock()
        request.user = Mock(username="DOMAIN\\user")

        class AuthenticatedView:
            """Dummy authenticated-only view marker."""

            authz_policy = "authenticated"

        AuthenticatedView.__module__ = "api.views.docs"

        def wrapped_view() -> None:
            return None

        wrapped_view.view_class = AuthenticatedView  # type: ignore[attr-defined]

        with patch("api.middleware.authorization.query_ldap_groups") as mock_ldap:
            with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
                result = middleware.process_view(request, wrapped_view, [], {})

        assert result is None
        assert mock_ldap.call_count == 0

    @override_settings(DEBUG=False)
    def test_authenticated_policy_rejects_unauthenticated_user(self) -> None:
        """authz_authenticated policy returns 401 when no user identity."""
        middleware = AuthorizationMiddleware(self.get_response)
        request = Mock()
        request.user = None

        class AuthenticatedView:
            """Dummy authenticated-only view marker."""

            authz_policy = "authenticated"

        AuthenticatedView.__module__ = "api.views.docs"

        def wrapped_view() -> None:
            return None

        wrapped_view.view_class = AuthenticatedView  # type: ignore[attr-defined]

        with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
            result = middleware.process_view(request, wrapped_view, [], {})

        assert result is not None
        assert result.status_code == 401

    @override_settings(DEBUG=False)
    def test_missing_view_policy_raises_improperly_configured(self) -> None:
        """Views in api.views must explicitly declare an authz policy."""
        middleware = AuthorizationMiddleware(self.get_response)
        request = Mock()
        request.user = Mock(username="DOMAIN\\user")

        class UndecoratedView:
            """Dummy undecorated view class for policy enforcement test."""

        UndecoratedView.__module__ = "api.views.user"

        def wrapped_view() -> None:
            """Dummy resolved callable used by Django for class-based views."""
            return None

        # Mirrors Django's runtime behavior where `as_view()` callables carry
        # a dynamically attached `view_class` attribute.
        wrapped_view.view_class = UndecoratedView  # type: ignore[attr-defined]

        from django.core.exceptions import ImproperlyConfigured

        with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
            with pytest.raises(ImproperlyConfigured):
                middleware.process_view(request, wrapped_view, [], {})

    @override_settings(DEBUG=False)
    def test_roles_policy_denies_when_required_role_missing(self) -> None:
        """authz_roles policy denies if user lacks all required roles."""
        middleware = AuthorizationMiddleware(self.get_response)
        request = Mock()
        request.user = Mock(username="DOMAIN\\viewer_user")
        view_func = _make_roles_view(roles=("app_admin",))

        with patch("api.middleware.authorization.query_ldap_groups") as mock_ldap:
            mock_ldap.return_value = ["CN=app-viewers,OU=Groups,DC=corp,DC=local"]
            with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
                result = middleware.process_view(request, view_func, [], {})

        assert result is not None
        assert result.status_code == 403

    @override_settings(DEBUG=False)
    def test_roles_policy_with_no_required_roles_raises_improperly_configured(
        self,
    ) -> None:
        """authz_roles policy must include at least one required role."""
        middleware = AuthorizationMiddleware(self.get_response)
        request = Mock()
        request.user = Mock(username="DOMAIN\\admin_user")

        class MisconfiguredRolesView:
            """Dummy roles policy view without authz_roles metadata."""

            authz_policy = "roles"

        MisconfiguredRolesView.__module__ = "api.views.sample"

        def wrapped_view() -> None:
            return None

        # Mirrors Django's runtime behavior where `as_view()` callables carry
        # a dynamically attached `view_class` attribute.
        wrapped_view.view_class = MisconfiguredRolesView  # type: ignore[attr-defined]

        with patch("api.middleware.authorization.query_ldap_groups") as mock_ldap:
            mock_ldap.return_value = ["CN=app-admins,OU=Groups,DC=corp,DC=local"]
            with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
                from django.core.exceptions import ImproperlyConfigured

                with pytest.raises(
                    ImproperlyConfigured, match="requires at least one role"
                ):
                    middleware.process_view(request, wrapped_view, [], {})

    @override_settings(DEBUG=False)
    def test_unknown_policy_raises_improperly_configured(self) -> None:
        """Unknown authz policy values are rejected."""
        middleware = AuthorizationMiddleware(self.get_response)
        request = Mock()
        request.user = Mock(username="DOMAIN\\admin_user")

        class UnknownPolicyView:
            """Dummy view with unsupported policy value."""

            authz_policy = "unknown"

        UnknownPolicyView.__module__ = "api.views.sample"

        def wrapped_view() -> None:
            return None

        # Mirrors Django's runtime behavior where `as_view()` callables carry
        # a dynamically attached `view_class` attribute.
        wrapped_view.view_class = UnknownPolicyView  # type: ignore[attr-defined]

        with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
            from django.core.exceptions import ImproperlyConfigured

            with pytest.raises(ImproperlyConfigured, match="Unknown authz policy"):
                middleware.process_view(request, wrapped_view, [], {})

    def test_is_project_view_returns_false_for_none(self) -> None:
        """_is_project_view handles None safely."""
        middleware = AuthorizationMiddleware(self.get_response)
        assert middleware._is_project_view(None) is False

    @override_settings(DEBUG=False)
    def test_authenticated_user_with_empty_username_returns_401(self) -> None:
        """Authenticated user with empty username returns 401."""
        middleware = AuthorizationMiddleware(self.get_response)
        request = Mock()
        request.user = Mock(is_authenticated=True, username="")
        view_func = _make_roles_view()

        with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
            result = middleware.process_view(request, view_func, [], {})

        assert result is not None
        assert result.status_code == 401


def test_query_ldap_groups_placeholder_returns_empty_list() -> None:
    """Default LDAP query placeholder returns an empty group list."""
    from api.middleware.authorization import query_ldap_groups

    assert query_ldap_groups("DOMAIN\\someone") == []


class TestAuthorizationMiddlewareHelpers:
    """Unit tests for middleware helper methods covering FBV code paths.

    The production views are all class-based, so the helpers' FBV branches
    (policy/roles set directly on the function object) are only reachable
    via these targeted unit tests.  They remain in the middleware to support
    function-based views written by future developers.
    """

    @staticmethod
    def get_response(request: Any) -> Mock:
        response = Mock()
        response.status_code = 200
        return response

    def test_get_view_policy_reads_attribute_directly_from_function(self) -> None:
        """_get_view_policy returns policy set directly on a FBV callable."""
        middleware = AuthorizationMiddleware(self.get_response)

        def fbv() -> None:
            return None

        fbv.authz_policy = "public"  # type: ignore[attr-defined]

        assert middleware._get_view_policy(fbv) == "public"

    def test_get_required_roles_reads_attribute_directly_from_function(self) -> None:
        """_get_required_roles returns roles set directly on a FBV callable."""
        middleware = AuthorizationMiddleware(self.get_response)

        def fbv() -> None:
            return None

        fbv.authz_roles = (ROLE_ADMIN,)  # type: ignore[attr-defined]

        assert middleware._get_required_roles(fbv) == (ROLE_ADMIN,)
