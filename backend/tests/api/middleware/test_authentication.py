"""Tests for the authentication middleware.

About request.META:
    request.META is a dictionary-like object in Django that contains HTTP request
    headers and server environment variables. It's part of the HttpRequest object.

    Common entries:
    - REMOTE_USER: Authenticated user identity (set by IIS/web server in production)
                   Example: "DOMAIN\\jsmith"
    - REMOTE_ADDR: Client IP address
    - HTTP_HOST: Host header
    - REQUEST_METHOD: HTTP method (GET, POST, etc.)
    - SERVER_NAME: Server hostname

    In tests:
    - We set request.META = {"REMOTE_USER": "..."} to simulate IIS authentication
    - In production, IIS handles Windows Authentication and injects REMOTE_USER
    - The middleware reads request.META.get("REMOTE_USER") to retrieve the username

    This is the standard Django pattern for accessing HTTP headers and IIS
    environment variables from the web server.
"""

from __future__ import annotations

import logging
from typing import Any, cast
from django.http import HttpRequest
from unittest.mock import Mock, patch

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from api.middleware.authentication import AuthenticationMiddleware


class TestAuthenticationMiddlewareDevMode:
    """Tests for authentication middleware in dev mode (AUTH_MODE=dev)."""

    @staticmethod
    def get_response(request: HttpRequest) -> Mock:
        """Mock ASGI application for middleware testing."""
        response = Mock()
        response.status_code = 200
        return response

    @override_settings(DEBUG=True)
    @pytest.mark.django_db
    def test_dev_mode_injects_mock_user(self) -> None:
        """In dev mode, middleware injects a mock user with DEV_USER_IDENTITY.

        The request should have a user object with username matching
        the DEV_USER_IDENTITY environment variable.
        """
        middleware = AuthenticationMiddleware(self.get_response)
        request = Mock()
        request.META = {}
        request.user = None

        with patch.dict(
            "os.environ", {"AUTH_MODE": "dev", "DEV_USER_IDENTITY": "dev_test_user"}
        ):
            middleware.process_request(request)

        assert request.user is not None
        assert request.user.username == "dev_test_user"

    @override_settings(DEBUG=True)
    @pytest.mark.django_db
    def test_dev_mode_default_identity(self) -> None:
        """When DEV_USER_IDENTITY is not set, defaults to 'dev_admin'.

        The middleware should use a sensible default if the environment
        variable is not configured.
        """
        middleware = AuthenticationMiddleware(self.get_response)
        request = Mock()
        request.META = {}
        request.user = None

        with patch.dict("os.environ", {"AUTH_MODE": "dev"}, clear=False):
            # Don't set DEV_USER_IDENTITY, should default to dev_admin
            middleware.process_request(request)

        assert request.user is not None
        assert request.user.username == "dev_admin"

    @override_settings(DEBUG=True)
    @pytest.mark.django_db
    def test_dev_mode_creates_django_user(self) -> None:
        """Dev mode creates or retrieves a Django User object.

        The middleware should ensure a proper Django User object exists
        in the database (or is retrieved if it already exists) so that
        downstream code can access user properties like id, is_active, etc.
        """
        middleware = AuthenticationMiddleware(self.get_response)
        request = Mock()
        request.META = {}
        request.user = None

        with patch.dict(
            "os.environ", {"AUTH_MODE": "dev", "DEV_USER_IDENTITY": "dev_test_user"}
        ):
            middleware.process_request(request)

        assert request.user is not None
        # User should be a real User instance (or have is_active, username, etc.)
        assert hasattr(request.user, "username")
        assert request.user.username == "dev_test_user"

    @override_settings(DEBUG=True)
    def test_dev_mode_rejects_invalid_identity(self) -> None:
        """Invalid DEV_USER_IDENTITY values are rejected at request time."""
        middleware = AuthenticationMiddleware(self.get_response)
        request = Mock()
        request.META = {}
        request.user = None

        with patch.dict(
            "os.environ", {"AUTH_MODE": "dev", "DEV_USER_IDENTITY": "bad/identity"}
        ):
            with pytest.raises(ImproperlyConfigured, match="DEV_USER_IDENTITY"):
                middleware.process_request(request)


class TestAuthenticationMiddlewareIISMode:
    """Tests for authentication middleware in IIS mode (AUTH_MODE=iis)."""

    @staticmethod
    def get_response(request: HttpRequest) -> Mock:
        """Mock ASGI application for middleware testing."""
        response = Mock()
        response.status_code = 200
        return response

    @override_settings(DEBUG=False)
    @pytest.mark.django_db
    @pytest.mark.parametrize(
        "remote_user",
        [
            "A" * 65,  # Overlong username (65 chars)
            "DOMAIN\\' OR 1=1--",  # SQL injection-like
            "DOMAIN\\user; DROP TABLE users;--",  # SQL injection-like
            "<script>alert(1)</script>",  # XSS-like
        ],
    )
    def test_iis_mode_rejects_overlong_and_injection_x_remote_user(
        self, remote_user: str
    ) -> None:
        """Overlong or dangerous X-Remote-User values are treated as anonymous."""
        get_response = self.get_response
        middleware = AuthenticationMiddleware(get_response)
        request = Mock()
        request.META = {"HTTP_X_REMOTE_USER": remote_user}
        request.user = None

        with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
            middleware.process_request(request)

        assert request.user is not None
        assert not request.user.is_authenticated

    @override_settings(DEBUG=False)
    def test_iis_mode_missing_x_remote_user_fails_closed(self) -> None:
        """Missing X-Remote-User header always results in unauthenticated user (fail closed)."""
        middleware = AuthenticationMiddleware(self.get_response)
        request = Mock()
        request.META = {}  # No X-Remote-User
        request.user = None

        with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
            middleware.process_request(request)

        assert request.user is not None
        assert not request.user.is_authenticated

    @override_settings(DEBUG=False)
    @pytest.mark.django_db
    def test_iis_mode_reads_x_remote_user(self) -> None:
        """In IIS mode, middleware reads the X-Remote-User header.

        The request.user.username should match the X-Remote-User value
        provided by IIS (typically DOMAIN\\username).
        """
        middleware = AuthenticationMiddleware(self.get_response)
        request = Mock()
        remote_user = "DOMAIN\\testuser"
        request.META = {"HTTP_X_REMOTE_USER": remote_user}
        request.user = None

        with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
            middleware.process_request(request)

        # In IIS mode, request.user should be set to reflect X-Remote-User
        assert request.user is not None
        assert request.user.username == remote_user

    @override_settings(DEBUG=False)
    def test_iis_mode_missing_x_remote_user_raises(self) -> None:
        """When X-Remote-User is missing in iis mode, authentication fails.

        Without X-Remote-User, the request is unauthenticated and should
        be rejected (by raising an exception or setting request.user to None).
        """
        middleware = AuthenticationMiddleware(self.get_response)
        request = Mock()
        request.META = {}  # No X-Remote-User
        request.user = None

        with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
            # In IIS mode without X_REMOTE_USER, should handle gracefully
            # (either leave user as None or raise)
            middleware.process_request(request)

        # User should be None or unauthenticated
        assert request.user is None or not request.user.is_authenticated

    @override_settings(DEBUG=False)
    @pytest.mark.django_db
    def test_iis_mode_creates_django_user_on_first_request(self) -> None:
        """First request with new X-Remote-User creates a Django User.

        The middleware should query or create a Django User object via
        RemoteUserBackend when a new X-Remote-User is encountered.
        """
        middleware = AuthenticationMiddleware(self.get_response)
        request = Mock()
        remote_user = "DOMAIN\\newuser"
        request.META = {"HTTP_X_REMOTE_USER": remote_user}
        request.user = None

        # Ensure the user doesn't exist
        User.objects.filter(username=remote_user).delete()

        with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
            middleware.process_request(request)

        # After processing, a User should exist with this username
        assert User.objects.filter(username=remote_user).exists()

    @override_settings(DEBUG=False)
    @pytest.mark.django_db
    def test_iis_mode_reuses_existing_user(self) -> None:
        """Subsequent requests with same X-Remote-User reuse the User.

        The middleware should not create duplicate User objects for the
        same X-Remote-User value.
        """
        middleware = AuthenticationMiddleware(self.get_response)
        remote_user = "DOMAIN\\existinguser"

        # Pre-create the user
        user, created = User.objects.get_or_create(username=remote_user)
        original_pk = user.pk
        assert original_pk is not None

        request = Mock()
        request.META = {"HTTP_X_REMOTE_USER": remote_user}
        request.user = None

        with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
            middleware.process_request(request)

        # Should reuse the existing user (same ID)
        assert User.objects.filter(username=remote_user, pk=original_pk).exists()

    @override_settings(DEBUG=False)
    @pytest.mark.django_db
    def test_iis_mode_rejects_invalid_x_remote_user(self) -> None:
        """Invalid X-Remote-User values are treated as anonymous."""
        middleware = AuthenticationMiddleware(self.get_response)
        request = Mock()
        request.META = {"HTTP_X_REMOTE_USER": "DOMAIN\\bad/user"}
        request.user = None

        with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
            middleware.process_request(request)

        assert request.user is not None
        assert not request.user.is_authenticated

    @override_settings(DEBUG=False)
    @pytest.mark.django_db
    def test_iis_mode_logs_authentication_success(
        self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Successful X-Remote-User resolution emits a structured auth success log."""
        monkeypatch.setattr(logging.getLogger("api"), "propagate", True)
        middleware = AuthenticationMiddleware(self.get_response)
        request = Mock()
        request.path = "/api/user/"
        request.META = {
            "HTTP_X_REMOTE_USER": "DOMAIN\\testuser",
            "REMOTE_ADDR": "198.51.100.2",
            "HTTP_USER_AGENT": "pytest-agent",
        }
        request.user = None

        with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
            with caplog.at_level(logging.INFO, logger="api.middleware.authentication"):
                middleware.process_request(request)

        record = cast(
            Any,
            next(
                r for r in caplog.records if r.name == "api.middleware.authentication"
            ),
        )
        assert record.event_type == "AUTHENTICATION_SUCCESS"
        assert record.user_identifier == "DOMAIN\\testuser"
        assert record.action_attempted == "authenticate X-Remote-User"
        assert record.result == "success"
        assert record.source_ip == "198.51.100.2"
        assert record.user_agent == "pytest-agent"

    @override_settings(DEBUG=False)
    @pytest.mark.django_db
    def test_iis_mode_logs_invalid_x_remote_user(
        self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Invalid X-Remote-User values emit a structured validation failure log."""
        monkeypatch.setattr(logging.getLogger("api"), "propagate", True)
        middleware = AuthenticationMiddleware(self.get_response)
        request = Mock()
        request.path = "/api/user/"
        request.META = {
            "HTTP_X_REMOTE_USER": "DOMAIN\\bad/user",
            "REMOTE_ADDR": "198.51.100.2",
            "HTTP_USER_AGENT": "pytest-agent",
        }
        request.user = None

        with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
            with caplog.at_level(
                logging.WARNING, logger="api.middleware.authentication"
            ):
                middleware.process_request(request)

        record = cast(
            Any,
            next(
                r for r in caplog.records if r.name == "api.middleware.authentication"
            ),
        )
        assert record.event_type == "INPUT_VALIDATION_FAILURE"
        assert record.user_identifier == "anonymous"
        assert record.action_attempted == "validate X-Remote-User"
        assert record.result == "failure"
        assert record.source_ip == "198.51.100.2"
        assert record.user_agent == "pytest-agent"
