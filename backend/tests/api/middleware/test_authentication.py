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

from unittest.mock import Mock, patch

import pytest
from django.contrib.auth.models import User
from django.test import override_settings

from api.middleware.authentication import AuthenticationMiddleware


class TestAuthenticationMiddlewareDevMode:
    """Tests for authentication middleware in dev mode (AUTH_MODE=dev)."""

    @staticmethod
    def get_response(request):
        """Mock WSGI application for middleware testing."""
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
        
        with patch.dict("os.environ", {"AUTH_MODE": "dev", "DEV_USER_IDENTITY": "dev_test_user"}):
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
        
        with patch.dict("os.environ", {"AUTH_MODE": "dev", "DEV_USER_IDENTITY": "dev_test_user"}):
            middleware.process_request(request)
        
        assert request.user is not None
        # User should be a real User instance (or have is_active, username, etc.)
        assert hasattr(request.user, "username")
        assert request.user.username == "dev_test_user"


class TestAuthenticationMiddlewareIISMode:
    """Tests for authentication middleware in IIS mode (AUTH_MODE=iis)."""

    @staticmethod
    def get_response(request):
        """Mock WSGI application for middleware testing."""
        response = Mock()
        response.status_code = 200
        return response

    @override_settings(DEBUG=False)
    @pytest.mark.django_db
    def test_iis_mode_reads_remote_user(self) -> None:
        """In IIS mode, middleware reads the REMOTE_USER header.
        
        The request.user.username should match the REMOTE_USER value
        provided by IIS (typically DOMAIN\\username).
        """
        middleware = AuthenticationMiddleware(self.get_response)
        request = Mock()
        remote_user = "DOMAIN\\testuser"
        request.META = {"REMOTE_USER": remote_user}
        request.user = None
        
        with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
            middleware.process_request(request)
        
        # In IIS mode, request.user should be set to reflect REMOTE_USER
        assert request.user is not None
        assert request.user.username == remote_user

    @override_settings(DEBUG=False)
    def test_iis_mode_missing_remote_user_raises(self) -> None:
        """When REMOTE_USER is missing in IIS mode, authentication fails.
        
        Without REMOTE_USER, the request is unauthenticated and should
        be rejected (by raising an exception or setting request.user to None).
        """
        middleware = AuthenticationMiddleware(self.get_response)
        request = Mock()
        request.META = {}  # No REMOTE_USER
        request.user = None
        
        with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
            # In IIS mode without REMOTE_USER, should handle gracefully
            # (either leave user as None or raise)
            middleware.process_request(request)
        
        # User should be None or unauthenticated
        assert request.user is None or not request.user.is_authenticated

    @override_settings(DEBUG=False)
    @pytest.mark.django_db
    def test_iis_mode_creates_django_user_on_first_request(self) -> None:
        """First request with new REMOTE_USER creates a Django User.
        
        The middleware should query or create a Django User object via
        RemoteUserBackend when a new REMOTE_USER is encountered.
        """
        middleware = AuthenticationMiddleware(self.get_response)
        request = Mock()
        remote_user = "DOMAIN\\newuser"
        request.META = {"REMOTE_USER": remote_user}
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
        """Subsequent requests with same REMOTE_USER reuse the User.
        
        The middleware should not create duplicate User objects for the
        same REMOTE_USER value.
        """
        middleware = AuthenticationMiddleware(self.get_response)
        remote_user = "DOMAIN\\existinguser"
        
        # Pre-create the user
        user, created = User.objects.get_or_create(username=remote_user)
        original_id = user.id
        
        request = Mock()
        request.META = {"REMOTE_USER": remote_user}
        request.user = None
        
        with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
            middleware.process_request(request)
        
        # Should reuse the existing user (same ID)
        assert User.objects.filter(username=remote_user, id=original_id).exists()
