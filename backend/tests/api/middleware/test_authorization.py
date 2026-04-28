"""Tests for the authorization middleware.

The authorization middleware enforces per-view authorization via the
``authz_policy`` attribute set by the permission decorators.  Every view
must resolve to one of ``@authz_public``, ``@authz_authenticated``, or
``@authz_roles(...)`` for authorization checks to proceed.

Role resolution happens only when a view requires roles:
- Dev mode: reads ``DEV_USER_ROLE`` environment variable and requires it to match ``api.constants.ROLES``
- IIS mode: queries LDAP (per-request) for AD group membership
"""

from __future__ import annotations

import logging
from typing import Any, cast
from unittest.mock import Mock, patch

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from api.constants import ADMIN_AD_GROUP, ROLE_ADMIN, ROLE_VIEWER, VIEWER_AD_GROUP
from api.middleware.authorization import AuthorizationMiddleware
from api.permissions import AUTHZ_POLICY_ATTR, AUTHZ_ROLES_ATTR


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
    # Django's as_view() dynamically attaches view_class to the callable at
    # runtime. We replicate that here so the middleware resolves policy/roles
    # from the class. All 'attr-defined' ignores in this file are the same pattern.
    wrapped_view.view_class = RolesView  # type: ignore[attr-defined]  # Mirrors Django as_view() runtime behavior where resolver callables carry view_class.
    return wrapped_view


class TestAuthorizationMiddlewareDevMode:
    """Tests for authorization middleware in dev mode (AUTH_MODE=dev)."""

    @staticmethod
    def get_response(request: Any) -> Mock:
        """Mock ASGI application for middleware testing."""
        response = Mock()
        response.status_code = 200
        return response

    @override_settings(DEBUG=True)
    def test_dev_mode_assigns_admin_role_from_env(self) -> None:
        """In dev mode with DEV_USER_ROLE=app_admin, user gets app_admin role."""
        middleware = AuthorizationMiddleware(self.get_response)
        request = Mock()
        request.user = Mock(username="dev_admin")
        view_func = _make_roles_view()

        with patch.dict(
            "os.environ", {"AUTH_MODE": "dev", "DEV_USER_ROLE": ROLE_ADMIN}
        ):
            result = middleware.process_view(request, view_func, [], {})

        assert result is None
        assert ROLE_ADMIN in request.user.roles

    @override_settings(DEBUG=True)
    def test_dev_mode_requires_explicit_role(self) -> None:
        """When DEV_USER_ROLE is not set, dev mode fails fast."""
        middleware = AuthorizationMiddleware(self.get_response)
        request = Mock()
        request.user = Mock(username="dev_admin")
        view_func = _make_roles_view()

        with patch.dict("os.environ", {"AUTH_MODE": "dev"}, clear=True):
            with pytest.raises(ImproperlyConfigured, match="DEV_USER_ROLE"):
                middleware.process_view(request, view_func, [], {})

    @override_settings(DEBUG=True)
    def test_dev_mode_viewer_role_from_env(self) -> None:
        """In dev mode with DEV_USER_ROLE=app_viewer, user gets app_viewer role."""
        middleware = AuthorizationMiddleware(self.get_response)
        request = Mock()
        request.user = Mock(username="dev_viewer")
        view_func = _make_roles_view()

        with patch.dict(
            "os.environ", {"AUTH_MODE": "dev", "DEV_USER_ROLE": ROLE_VIEWER}
        ):
            result = middleware.process_view(request, view_func, [], {})

        assert result is None
        assert request.user.roles == [ROLE_VIEWER]

    @override_settings(DEBUG=True)
    def test_dev_mode_rejects_non_canonical_role(self) -> None:
        """In dev mode, legacy shorthand roles are rejected."""
        middleware = AuthorizationMiddleware(self.get_response)
        request = Mock()
        request.user = Mock(username="dev_admin")
        view_func = _make_roles_view()

        with patch.dict("os.environ", {"AUTH_MODE": "dev", "DEV_USER_ROLE": "admin"}):
            with pytest.raises(ImproperlyConfigured, match="DEV_USER_ROLE"):
                middleware.process_view(request, view_func, [], {})


class TestAuthorizationMiddlewareIISMode:
    """Tests for authorization middleware in IIS mode (AUTH_MODE=iis)."""

    @staticmethod
    def get_response(request: Any) -> Mock:
        """Mock ASGI application for middleware testing."""
        response = Mock()
        response.status_code = 200
        return response

    @override_settings(DEBUG=False)
    def test_user_with_admin_group_gets_admin_role(self) -> None:
        """User in LDAP admin group receives app_admin role."""
        middleware = AuthorizationMiddleware(self.get_response)
        request = Mock()
        request.user = Mock(username="DOMAIN\\admin_user")
        view_func = _make_roles_view()

        with patch("api.middleware.authorization.query_ldap_groups") as mock_ldap:
            mock_ldap.return_value = [ADMIN_AD_GROUP]
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
            mock_ldap.return_value = [VIEWER_AD_GROUP]
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
                ADMIN_AD_GROUP,
                VIEWER_AD_GROUP,
            ]
            with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
                result = middleware.process_view(request, view_func, [], {})

        assert result is None
        assert ROLE_ADMIN in request.user.roles
        assert ROLE_VIEWER in request.user.roles

    @override_settings(DEBUG=False)
    def test_user_with_no_matching_groups_returns_403(
        self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """User authenticated but not in any configured AD group gets 403 JSON."""
        monkeypatch.setattr(logging.getLogger("api"), "propagate", True)
        middleware = AuthorizationMiddleware(self.get_response)
        request = Mock()
        request.user = Mock(username="DOMAIN\\regular_user")
        request.path = "/api/admin/"
        request.META = {
            "REMOTE_ADDR": "203.0.113.9",
            "HTTP_USER_AGENT": "pytest-agent",
        }
        view_func = _make_roles_view()

        with patch("api.middleware.authorization.query_ldap_groups") as mock_ldap:
            mock_ldap.return_value = ["CN=other-group,OU=Groups,DC=corp,DC=local"]
            with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
                with caplog.at_level(
                    logging.WARNING, logger="api.middleware.authorization"
                ):
                    result = middleware.process_view(request, view_func, [], {})

        assert result is not None
        assert result.status_code == 403
        import json

        body = json.loads(result.content)
        assert body["detail"] == "You do not have permission to perform this action."

        record = cast(
            Any,
            next(r for r in caplog.records if r.name == "api.middleware.authorization"),
        )
        assert record.event_type == "AUTHORIZATION_FAILURE"
        assert record.user_identifier == "DOMAIN\\regular_user"
        assert record.action_attempted == "authorize request"
        assert record.result == "failure"
        assert record.status_code == 403

    @override_settings(DEBUG=False)
    def test_unauthenticated_request_returns_401(
        self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Request without user identity returns 401 JSON response."""
        monkeypatch.setattr(logging.getLogger("api"), "propagate", True)
        middleware = AuthorizationMiddleware(self.get_response)
        request = Mock()
        request.user = None
        request.path = "/api/user/"
        request.META = {
            "REMOTE_ADDR": "203.0.113.11",
            "HTTP_USER_AGENT": "pytest-agent",
        }
        view_func = _make_roles_view()

        with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
            with caplog.at_level(
                logging.WARNING, logger="api.middleware.authorization"
            ):
                result = middleware.process_view(request, view_func, [], {})

        assert result is not None
        assert result.status_code == 401

        record = cast(
            Any,
            next(r for r in caplog.records if r.name == "api.middleware.authorization"),
        )
        assert record.event_type == "AUTHENTICATION_FAILURE"
        assert record.user_identifier == "anonymous"
        assert record.action_attempted == "authenticate request"
        assert record.result == "failure"
        assert record.status_code == 401

    @override_settings(DEBUG=False)
    def test_ldap_queried_on_every_request(self) -> None:
        """LDAP is queried on every request — results are not cached."""
        middleware = AuthorizationMiddleware(self.get_response)
        view_func = _make_roles_view()

        with patch("api.middleware.authorization.query_ldap_groups") as mock_ldap:
            mock_ldap.return_value = [ADMIN_AD_GROUP]

            with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
                request1 = Mock()
                request1.user = Mock(username="DOMAIN\\repeat_user")
                middleware.process_view(request1, view_func, [], {})
                assert mock_ldap.call_count == 1

                request2 = Mock()
                request2.user = Mock(username="DOMAIN\\repeat_user")
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
        wrapped_view.view_class = PublicView  # type: ignore[attr-defined]  # Mirrors Django as_view() runtime behavior where resolver callables carry view_class.

        with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
            result = middleware.process_view(request, wrapped_view, [], {})

        assert result is None

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

        # Emulates Django's as_view() runtime attachment (see _make_roles_view).
        wrapped_view.view_class = AuthenticatedView  # type: ignore[attr-defined]  # Mirrors Django as_view() runtime behavior where resolver callables carry view_class.

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

        # Emulates Django's as_view() runtime attachment (see _make_roles_view).
        wrapped_view.view_class = AuthenticatedView  # type: ignore[attr-defined]  # Mirrors Django as_view() runtime behavior where resolver callables carry view_class.

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
        wrapped_view.view_class = UndecoratedView  # type: ignore[attr-defined]  # Mirrors Django as_view() runtime behavior where resolver callables carry view_class.

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
            mock_ldap.return_value = [VIEWER_AD_GROUP]
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
        wrapped_view.view_class = MisconfiguredRolesView  # type: ignore[attr-defined]  # Mirrors Django as_view() runtime behavior where resolver callables carry view_class.

        with patch("api.middleware.authorization.query_ldap_groups") as mock_ldap:
            mock_ldap.return_value = [ADMIN_AD_GROUP]
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
        wrapped_view.view_class = UnknownPolicyView  # type: ignore[attr-defined]  # Mirrors Django as_view() runtime behavior where resolver callables carry view_class.

        with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
            from django.core.exceptions import ImproperlyConfigured

            with pytest.raises(ImproperlyConfigured, match="Unknown authz policy"):
                middleware.process_view(request, wrapped_view, [], {})

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


def test_query_ldap_groups_returns_empty_when_not_configured() -> None:
    """LDAP query returns empty list when settings are not configured."""
    from api.middleware.authorization import query_ldap_groups

    with override_settings(LDAP_SERVER_URI="", LDAP_BASE_DN=""):
        assert query_ldap_groups("DOMAIN\\someone") == []


class TestQueryLdapGroups:
    """Tests for the real LDAP query function."""

    def test_returns_empty_when_server_uri_not_configured(self) -> None:
        """Returns [] when LDAP_SERVER_URI is blank."""
        from api.middleware.authorization import query_ldap_groups

        with override_settings(LDAP_SERVER_URI="", LDAP_BASE_DN="DC=corp,DC=local"):
            assert query_ldap_groups("DOMAIN\\jsmith") == []

    def test_returns_empty_when_base_dn_not_configured(self) -> None:
        """Returns [] when LDAP_BASE_DN is blank."""
        from api.middleware.authorization import query_ldap_groups

        with override_settings(
            LDAP_SERVER_URI="ldaps://dc.corp.local", LDAP_BASE_DN=""
        ):
            assert query_ldap_groups("DOMAIN\\jsmith") == []

    def test_raises_on_connection_failure(self) -> None:
        """Raises when the LDAP server is unreachable."""
        from api.middleware.authorization import query_ldap_groups

        with override_settings(
            LDAP_SERVER_URI="ldaps://dc.corp.local",
            LDAP_BASE_DN="DC=corp,DC=local",
        ):
            with patch(
                "api.middleware.authorization.Connection",
                side_effect=Exception("connection refused"),
            ):
                with pytest.raises(Exception, match="connection refused"):
                    query_ldap_groups("DOMAIN\\jsmith")

    def test_returns_empty_when_no_entries_found(self) -> None:
        """Returns [] when the user has no LDAP entries."""
        from api.middleware.authorization import query_ldap_groups

        mock_conn = Mock()
        mock_conn.entries = []

        with override_settings(
            LDAP_SERVER_URI="ldaps://dc.corp.local",
            LDAP_BASE_DN="DC=corp,DC=local",
        ):
            with patch(
                "api.middleware.authorization.Connection", return_value=mock_conn
            ):
                assert query_ldap_groups("DOMAIN\\jsmith") == []
                mock_conn.unbind.assert_called_once()

    def test_returns_groups_on_successful_lookup(self) -> None:
        """Returns group DNs from the memberOf attribute."""
        from api.middleware.authorization import query_ldap_groups

        expected_groups = [
            ADMIN_AD_GROUP,
            "CN=domain-users,OU=Groups,DC=corp,DC=local",
        ]
        mock_entry = Mock()
        mock_entry.memberOf.values = expected_groups
        mock_conn = Mock()
        mock_conn.entries = [mock_entry]

        with override_settings(
            LDAP_SERVER_URI="ldaps://dc.corp.local",
            LDAP_BASE_DN="DC=corp,DC=local",
        ):
            with patch(
                "api.middleware.authorization.Connection", return_value=mock_conn
            ):
                result = query_ldap_groups("DOMAIN\\jsmith")

        assert result == expected_groups
        mock_conn.unbind.assert_called_once()

    def test_extracts_sam_account_name_from_domain_username(self) -> None:
        """Strips DOMAIN\\ prefix when building the LDAP filter."""
        from api.middleware.authorization import query_ldap_groups

        mock_conn = Mock()
        mock_conn.entries = []

        with override_settings(
            LDAP_SERVER_URI="ldaps://dc.corp.local",
            LDAP_BASE_DN="DC=corp,DC=local",
        ):
            with patch(
                "api.middleware.authorization.Connection", return_value=mock_conn
            ):
                query_ldap_groups("DOMAIN\\jsmith")

        call_kwargs = mock_conn.search.call_args[1]
        assert "jsmith" in call_kwargs["search_filter"]
        assert "DOMAIN" not in call_kwargs["search_filter"]

    def test_handles_username_without_domain_prefix(self) -> None:
        """Works with a plain username (no DOMAIN\\ prefix)."""
        from api.middleware.authorization import query_ldap_groups

        mock_conn = Mock()
        mock_conn.entries = []

        with override_settings(
            LDAP_SERVER_URI="ldaps://dc.corp.local",
            LDAP_BASE_DN="DC=corp,DC=local",
        ):
            with patch(
                "api.middleware.authorization.Connection", return_value=mock_conn
            ):
                query_ldap_groups("jsmith")

        call_kwargs = mock_conn.search.call_args[1]
        assert "jsmith" in call_kwargs["search_filter"]

    def test_raises_on_search_exception(self) -> None:
        """Raises when the search itself fails (unbind still called)."""
        from api.middleware.authorization import query_ldap_groups

        mock_conn = Mock()
        mock_conn.search.side_effect = Exception("search timeout")

        with override_settings(
            LDAP_SERVER_URI="ldaps://dc.corp.local",
            LDAP_BASE_DN="DC=corp,DC=local",
        ):
            with patch(
                "api.middleware.authorization.Connection", return_value=mock_conn
            ):
                with pytest.raises(Exception, match="search timeout"):
                    query_ldap_groups("DOMAIN\\jsmith")
                mock_conn.unbind.assert_called_once()

    def test_unbind_called_even_on_search_failure(self) -> None:
        """Connection is always unbound even when the search raises."""
        from api.middleware.authorization import query_ldap_groups

        mock_conn = Mock()
        mock_conn.search.side_effect = RuntimeError("network error")

        with override_settings(
            LDAP_SERVER_URI="ldaps://dc.corp.local",
            LDAP_BASE_DN="DC=corp,DC=local",
        ):
            with patch(
                "api.middleware.authorization.Connection", return_value=mock_conn
            ):
                with pytest.raises(RuntimeError, match="network error"):
                    query_ldap_groups("DOMAIN\\jsmith")
                mock_conn.unbind.assert_called_once()


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

    def test_get_view_attr_reads_policy_from_function(self) -> None:
        """_get_view_attr returns policy set directly on a FBV callable."""
        middleware = AuthorizationMiddleware(self.get_response)

        def fbv() -> None:
            return None

        # Simulates @authz_public setting the attribute directly on a FBV.
        fbv.authz_policy = "public"  # type: ignore[attr-defined]  # Simulates decorator-injected function metadata used by middleware resolution.

        assert middleware._get_view_attr(fbv, AUTHZ_POLICY_ATTR, str) == "public"

    def test_get_view_attr_reads_roles_from_function(self) -> None:
        """_get_view_attr returns roles set directly on a FBV callable."""
        middleware = AuthorizationMiddleware(self.get_response)

        def fbv() -> None:
            return None

        # Simulates @authz_roles setting the attribute directly on a FBV.
        fbv.authz_roles = (ROLE_ADMIN,)  # type: ignore[attr-defined]  # Simulates decorator-injected function metadata used by middleware resolution.

        assert middleware._get_view_attr(fbv, AUTHZ_ROLES_ATTR, tuple) == (ROLE_ADMIN,)


class TestAuthorizationMiddlewareAuditLogging:
    """Tests for WARNING audit logs emitted on 401 and 403 responses."""

    @staticmethod
    def get_response(request: Any) -> Mock:
        response = Mock()
        response.status_code = 200
        return response

    @pytest.fixture(autouse=True)
    def enable_log_propagation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Re-enable propagation so caplog captures records from the api logger.

        The LOGGING config sets propagate=False on the 'api' logger. Tests that
        need caplog must temporarily restore propagation so records reach the root
        logger where pytest's capture handler lives.
        """
        monkeypatch.setattr(logging.getLogger("api"), "propagate", True)

    @override_settings(DEBUG=False)
    def test_401_response_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Unauthenticated request triggers a WARNING log containing the path."""
        middleware = AuthorizationMiddleware(self.get_response)
        request = Mock()
        request.user = None
        request.method = "GET"
        request.path = "/api/user/"
        view_func = _make_roles_view()

        with caplog.at_level(logging.WARNING, logger="api.middleware.authorization"):
            with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
                result = middleware.process_view(request, view_func, [], {})

        assert result is not None
        assert result.status_code == 401
        records = [
            cast(Any, r)
            for r in caplog.records
            if r.name == "api.middleware.authorization"
        ]
        assert len(records) == 1
        assert records[0].levelno == logging.WARNING
        assert records[0].event_type == "AUTHENTICATION_FAILURE"
        assert records[0].action_attempted == "authenticate request"
        assert records[0].result == "failure"
        assert records[0].status_code == 401
        assert records[0].resource_accessed == "/api/user/"

    @override_settings(DEBUG=False)
    def test_403_response_logs_warning_with_username(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Authenticated user denied by role triggers a WARNING log with username and path."""
        middleware = AuthorizationMiddleware(self.get_response)
        request = Mock()
        request.user = Mock(username="DOMAIN\\denied_user")
        request.method = "GET"
        request.path = "/api/user/"
        view_func = _make_roles_view()

        with caplog.at_level(logging.WARNING, logger="api.middleware.authorization"):
            with patch("api.middleware.authorization.query_ldap_groups") as mock_ldap:
                mock_ldap.return_value = ["CN=other-group,OU=Groups,DC=corp,DC=local"]
                with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
                    result = middleware.process_view(request, view_func, [], {})

        assert result is not None
        assert result.status_code == 403
        records = [
            cast(Any, r)
            for r in caplog.records
            if r.name == "api.middleware.authorization"
        ]
        assert len(records) == 1
        assert records[0].levelno == logging.WARNING
        assert records[0].event_type == "AUTHORIZATION_FAILURE"
        assert records[0].user_identifier == "DOMAIN\\denied_user"
        assert records[0].action_attempted == "authorize request"
        assert records[0].result == "failure"
        assert records[0].status_code == 403
        assert records[0].resource_accessed == "/api/user/"

    @override_settings(DEBUG=False)
    def test_500_response_logs_error(self, caplog: pytest.LogCaptureFixture) -> None:
        """Unhandled exception triggers an ERROR log with traceback."""
        middleware = AuthorizationMiddleware(self.get_response)
        request = Mock()
        request.user = Mock(username="DOMAIN\\admin_user")
        request.method = "GET"
        request.path = "/api/user/"
        view_func = _make_roles_view()

        with caplog.at_level(logging.ERROR, logger="api.middleware.authorization"):
            with patch("api.middleware.authorization.query_ldap_groups") as mock_ldap:
                mock_ldap.side_effect = RuntimeError("LDAP server crashed")
                with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
                    result = middleware.process_view(request, view_func, [], {})

        assert result is not None
        assert result.status_code == 500
        records = [
            cast(Any, r)
            for r in caplog.records
            if r.name == "api.middleware.authorization"
        ]
        assert len(records) == 1
        assert records[0].levelno == logging.ERROR


class TestAuthorizationMiddlewareErrorResponseShape:
    """Tests that 401/403 error responses include the request_id field."""

    @staticmethod
    def get_response(request: Any) -> Mock:
        response = Mock()
        response.status_code = 200
        return response

    @override_settings(DEBUG=False)
    def test_401_response_includes_request_id(self) -> None:
        """401 JSON body contains a request_id key."""
        import json

        middleware = AuthorizationMiddleware(self.get_response)
        request = Mock()
        request.user = None
        request.method = "GET"
        request.path = "/api/user/"
        view_func = _make_roles_view()

        with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
            result = middleware.process_view(request, view_func, [], {})

        assert result is not None
        assert result.status_code == 401
        body = json.loads(result.content)
        assert "request_id" in body

    @override_settings(DEBUG=False)
    def test_403_response_includes_request_id(self) -> None:
        """403 JSON body contains a request_id key."""
        import json

        middleware = AuthorizationMiddleware(self.get_response)
        request = Mock()
        request.user = Mock(username="DOMAIN\\regular_user")
        request.method = "GET"
        request.path = "/api/user/"
        view_func = _make_roles_view()

        with patch("api.middleware.authorization.query_ldap_groups") as mock_ldap:
            mock_ldap.return_value = ["CN=other-group,OU=Groups,DC=corp,DC=local"]
            with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
                result = middleware.process_view(request, view_func, [], {})

        assert result is not None
        assert result.status_code == 403
        body = json.loads(result.content)
        assert "request_id" in body

    @override_settings(DEBUG=False)
    def test_500_response_on_unhandled_exception(self) -> None:
        """Unhandled exception returns 500 JSON envelope with request_id."""
        import json

        middleware = AuthorizationMiddleware(self.get_response)
        request = Mock()
        request.user = Mock(username="DOMAIN\\admin_user")
        request.method = "GET"
        request.path = "/api/user/"
        view_func = _make_roles_view()

        with patch("api.middleware.authorization.query_ldap_groups") as mock_ldap:
            mock_ldap.side_effect = RuntimeError("LDAP server crashed")
            with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
                result = middleware.process_view(request, view_func, [], {})

        assert result is not None
        assert result.status_code == 500
        body = json.loads(result.content)
        assert body["detail"] == "An unexpected error occurred."
        assert "request_id" in body

    @override_settings(DEBUG=False)
    def test_500_response_does_not_leak_internal_details(self) -> None:
        """500 response body contains only the safe message, not the traceback."""
        import json

        middleware = AuthorizationMiddleware(self.get_response)
        request = Mock()
        request.user = Mock(username="DOMAIN\\admin_user")
        request.method = "GET"
        request.path = "/api/user/"
        view_func = _make_roles_view()

        with patch("api.middleware.authorization.query_ldap_groups") as mock_ldap:
            mock_ldap.side_effect = ConnectionError("secret internal detail")
            with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
                result = middleware.process_view(request, view_func, [], {})

        assert result is not None
        assert result.status_code == 500
        body = json.loads(result.content)
        assert "secret internal detail" not in json.dumps(body)
