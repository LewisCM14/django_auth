"""Tests for the authorization middleware.

About authorization middleware:
    The authorization middleware runs AFTER authentication middleware in the
    pipeline. At this point:
    - request.user is populated (from authentication middleware)
    - We need to fetch the user's roles based on their identity
    
    In dev mode:
    - Roles come from DEV_USER_ROLE environment variable (defaults to 'admin')
    
    In IIS mode:
    - Roles come from LDAP group membership query
    - Results are cached to avoid querying AD on every request
    - Cache TTL is configurable via LDAP_CACHE_TTL setting
    
    The middleware attaches roles to request.user as request.user.roles, which
    DRF permission classes can then check to enforce access control.
    
    Public access is now explicit via @authz_public on views.
"""
from __future__ import annotations

from unittest.mock import Mock, patch

import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import override_settings

from api.constants import ROLE_ADMIN, ROLE_VIEWER, ROLES
from api.middleware.authorization import AuthorizationMiddleware


class TestAuthorizationMiddlewareDevMode:
    """Tests for authorization middleware in dev mode (AUTH_MODE=dev)."""

    @staticmethod
    def get_response(request):
        """Mock WSGI application for middleware testing."""
        response = Mock()
        response.status_code = 200
        return response

    def setup_method(self):
        """Clear cache before each test."""
        cache.clear()

    @override_settings(DEBUG=True)
    def test_dev_mode_assigns_role_from_env(self) -> None:
        """In dev mode, roles come from DEV_USER_ROLE environment variable.
        
        The middleware should read DEV_USER_ROLE (e.g., 'admin' or 'viewer')
        and assign the corresponding application role to request.user.roles.
        """
        middleware = AuthorizationMiddleware(self.get_response)
        request = Mock()
        request.user = Mock(username="dev_admin")
        request.path = "/api/user/"
        
        with patch.dict("os.environ", {"AUTH_MODE": "dev", "DEV_USER_ROLE": "admin"}):
            middleware.process_request(request)
        
        assert hasattr(request.user, "roles")
        assert ROLE_ADMIN in request.user.roles

    @override_settings(DEBUG=True)
    def test_dev_mode_defaults_to_admin(self) -> None:
        """When DEV_USER_ROLE is not set in dev mode, defaults to 'admin'.
        
        The middleware should use a sensible default for development if the
        environment variable is not configured.
        """
        middleware = AuthorizationMiddleware(self.get_response)
        request = Mock()
        request.user = Mock(username="dev_admin")
        request.path = "/api/user/"
        
        with patch.dict("os.environ", {"AUTH_MODE": "dev"}, clear=False):
            # Don't set DEV_USER_ROLE, should default to admin
            middleware.process_request(request)
        
        assert hasattr(request.user, "roles")
        assert ROLE_ADMIN in request.user.roles


class TestAuthorizationMiddlewareIISMode:
    """Tests for authorization middleware in IIS mode (AUTH_MODE=iis)."""

    @staticmethod
    def get_response(request):
        """Mock WSGI application for middleware testing."""
        response = Mock()
        response.status_code = 200
        return response

    def setup_method(self):
        """Clear cache before each test."""
        cache.clear()

    @override_settings(DEBUG=False)
    def test_user_with_admin_group_gets_admin_role(self) -> None:
        """User with admin group in LDAP gets app_admin role.
        
        The middleware should query LDAP, find the user in the admin group,
        map that to app_admin role, and attach it to request.user.roles.
        """
        middleware = AuthorizationMiddleware(self.get_response)
        request = Mock()
        request.user = Mock(username="DOMAIN\\admin_user")
        request.path = "/api/user/"
        
        # Mock LDAP to return admin group
        with patch("api.middleware.authorization.query_ldap_groups") as mock_ldap:
            mock_ldap.return_value = ["CN=app-admins,OU=Groups,DC=corp,DC=local"]
            with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
                middleware.process_request(request)
        
        assert hasattr(request.user, "roles")
        assert ROLE_ADMIN in request.user.roles

    @override_settings(DEBUG=False)
    def test_user_with_viewer_group_gets_viewer_role(self) -> None:
        """User with viewer group in LDAP gets app_viewer role.
        
        Similar to admin test, but for viewer role.
        """
        middleware = AuthorizationMiddleware(self.get_response)
        request = Mock()
        request.user = Mock(username="DOMAIN\\viewer_user")
        request.path = "/api/user/"
        
        # Mock LDAP to return viewer group
        with patch("api.middleware.authorization.query_ldap_groups") as mock_ldap:
            mock_ldap.return_value = ["CN=app-viewers,OU=Groups,DC=corp,DC=local"]
            with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
                middleware.process_request(request)
        
        assert hasattr(request.user, "roles")
        assert ROLE_VIEWER in request.user.roles

    @override_settings(DEBUG=False)
    def test_user_with_multiple_groups_gets_multiple_roles(self) -> None:
        """User in multiple groups gets all corresponding roles.
        
        A user could be in both admin and viewer groups, so they should
        get both roles.
        """
        middleware = AuthorizationMiddleware(self.get_response)
        request = Mock()
        request.user = Mock(username="DOMAIN\\power_user")
        request.path = "/api/user/"
        
        # Mock LDAP to return both groups
        with patch("api.middleware.authorization.query_ldap_groups") as mock_ldap:
            mock_ldap.return_value = [
                "CN=app-admins,OU=Groups,DC=corp,DC=local",
                "CN=app-viewers,OU=Groups,DC=corp,DC=local",
            ]
            with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
                middleware.process_request(request)
        
        assert hasattr(request.user, "roles")
        assert ROLE_ADMIN in request.user.roles
        assert ROLE_VIEWER in request.user.roles

    @override_settings(DEBUG=False)
    def test_user_with_no_matching_groups_returns_403(self) -> None:
        """User authenticated but not in any configured AD group → 403 Forbidden.
        
        LDAP query succeeds but returns groups that don't map to app roles.
        The middleware should raise a PermissionDenied exception (caught by DRF).
        """
        middleware = AuthorizationMiddleware(self.get_response)
        request = Mock()
        request.user = Mock(username="DOMAIN\\regular_user")
        request.path = "/api/user/"
        
        # Mock LDAP to return non-matching group
        with patch("api.middleware.authorization.query_ldap_groups") as mock_ldap:
            mock_ldap.return_value = ["CN=other-group,OU=Groups,DC=corp,DC=local"]
            with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
                from django.core.exceptions import PermissionDenied
                with pytest.raises(PermissionDenied):
                    middleware.process_request(request)

    @override_settings(DEBUG=False)
    def test_unauthenticated_request_returns_401(self) -> None:
        """Request without user is rejected with 401.
        
        If request.user is None or not set, the middleware should raise
        an AuthenticationFailed exception (caught by DRF as 401).
        """
        middleware = AuthorizationMiddleware(self.get_response)
        request = Mock()
        request.user = None
        request.path = "/api/user/"
        
        from rest_framework.exceptions import AuthenticationFailed
        with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
            with pytest.raises(AuthenticationFailed):
                middleware.process_request(request)

    @override_settings(DEBUG=False)
    def test_ldap_result_is_cached(self) -> None:
        """LDAP query result for a user is cached.
        
        Second request for same user should not trigger LDAP query.
        """
        middleware = AuthorizationMiddleware(self.get_response)
        request = Mock()
        username = "DOMAIN\\cached_user"
        request.user = Mock(username=username)
        request.path = "/api/user/"
        
        with patch("api.middleware.authorization.query_ldap_groups") as mock_ldap:
            mock_ldap.return_value = ["CN=app-admins,OU=Groups,DC=corp,DC=local"]
            
            with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
                # First request
                middleware.process_request(request)
                assert mock_ldap.call_count == 1
                
                # Second request (same user)
                request2 = Mock()
                request2.user = Mock(username=username)
                request2.path = "/api/user/"
                middleware.process_request(request2)
                # Should still be 1 (not called again due to cache)
                assert mock_ldap.call_count == 1

    @override_settings(DEBUG=False)
    def test_cache_respects_ttl(self) -> None:
        """Cache entry expires after LDAP_CACHE_TTL seconds.
        
        After TTL expiry, next request for same user should query LDAP again.
        """
        middleware = AuthorizationMiddleware(self.get_response)
        request = Mock()
        username = "DOMAIN\\ttl_user"
        request.user = Mock(username=username)
        request.path = "/api/user/"
        
        with patch("api.middleware.authorization.query_ldap_groups") as mock_ldap:
            mock_ldap.return_value = ["CN=app-admins,OU=Groups,DC=corp,DC=local"]
            
            with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
                # First request caches result
                middleware.process_request(request)
                assert mock_ldap.call_count == 1
                
                # Clear cache to simulate TTL expiry
                cache.delete(f"ldap_groups_{username}")
                
                # Second request should query LDAP again
                request2 = Mock()
                request2.user = Mock(username=username)
                request2.path = "/api/user/"
                middleware.process_request(request2)
                assert mock_ldap.call_count == 2

    @override_settings(DEBUG=False)
    def test_health_endpoint_bypasses_authorization(self) -> None:
        """Public policy bypasses authorization checks."""
        middleware = AuthorizationMiddleware(self.get_response)
        request = Mock()
        request.user = None  # No user
        request.path = "/api/health/"

        class PublicView:
            """Dummy class-based view marker for public policy."""

            authz_policy = "public"

        PublicView.__module__ = "api.views.health"

        def wrapped_view() -> None:
            """Dummy resolved callable used by Django for class-based views."""
            return None

        wrapped_view.view_class = PublicView  # type: ignore[attr-defined]

        with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
            middleware.process_view(request, wrapped_view, [], {})

    @override_settings(DEBUG=False)
    def test_non_project_view_raises_improperly_configured(self) -> None:
        """Strict mode requires all routed views to live under api.views."""
        middleware = AuthorizationMiddleware(self.get_response)
        request = Mock()
        request.user = None
        request.path = "/api/private/"

        def wrapped_view() -> None:
            """Dummy resolved callable for third-party view simulation."""
            return None

        wrapped_view.__module__ = "third_party.module"

        from django.core.exceptions import ImproperlyConfigured
        with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
            with pytest.raises(ImproperlyConfigured):
                middleware.process_view(request, wrapped_view, [], {})

    @override_settings(DEBUG=False)
    def test_missing_view_policy_raises_improperly_configured(self) -> None:
        """Views in api.views must explicitly declare an authz policy."""
        middleware = AuthorizationMiddleware(self.get_response)
        request = Mock()
        request.user = Mock(username="DOMAIN\\user")
        request.path = "/api/user/"

        class UndecoratedView:
            """Dummy undecorated view class for policy enforcement test."""

        UndecoratedView.__module__ = "api.views.user"

        def wrapped_view() -> None:
            """Dummy resolved callable used by Django for class-based views."""
            return None

        wrapped_view.view_class = UndecoratedView  # type: ignore[attr-defined]

        from django.core.exceptions import ImproperlyConfigured
        with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
            with pytest.raises(ImproperlyConfigured):
                middleware.process_view(request, wrapped_view, [], {})

    @override_settings(DEBUG=False)
    def test_authenticated_policy_allows_authenticated_user_without_roles(self) -> None:
        """authz_authenticated policy allows access with identity only."""
        middleware = AuthorizationMiddleware(self.get_response)
        request = Mock()
        request.user = Mock(username="DOMAIN\\user")
        request.path = "/api/any-auth/"

        class AuthenticatedView:
            """Dummy authenticated-only view marker."""

            authz_policy = "authenticated"

        AuthenticatedView.__module__ = "api.views.sample"

        def wrapped_view() -> None:
            """Dummy resolved callable used by Django for class-based views."""
            return None

        wrapped_view.view_class = AuthenticatedView  # type: ignore[attr-defined]

        with patch("api.middleware.authorization.query_ldap_groups") as mock_ldap:
            with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
                middleware.process_view(request, wrapped_view, [], {})
        assert mock_ldap.call_count == 0

    @override_settings(DEBUG=False)
    def test_roles_policy_denies_when_required_role_missing(self) -> None:
        """authz_roles policy denies if user lacks all required roles."""
        middleware = AuthorizationMiddleware(self.get_response)
        request = Mock()
        request.user = Mock(username="DOMAIN\\viewer_user")
        request.path = "/api/admin-only/"

        class AdminOnlyView:
            """Dummy role-protected view marker."""

            authz_policy = "roles"
            authz_roles = ("app_admin",)

        AdminOnlyView.__module__ = "api.views.sample"

        def wrapped_view() -> None:
            """Dummy resolved callable used by Django for class-based views."""
            return None

        wrapped_view.view_class = AdminOnlyView  # type: ignore[attr-defined]

        with patch("api.middleware.authorization.query_ldap_groups") as mock_ldap:
            mock_ldap.return_value = ["CN=app-viewers,OU=Groups,DC=corp,DC=local"]
            with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
                from django.core.exceptions import PermissionDenied

                with pytest.raises(PermissionDenied):
                    middleware.process_view(request, wrapped_view, [], {})
