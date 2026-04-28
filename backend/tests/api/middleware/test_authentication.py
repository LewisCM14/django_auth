"""Tests for authentication middleware behavior."""

from __future__ import annotations

import logging
from typing import Any, cast
from unittest.mock import Mock, patch

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpRequest
from django.test import override_settings

from api.middleware.authentication import AuthenticationMiddleware


class TestAuthenticationMiddlewareDevMode:
    """Tests for authentication middleware in dev mode (AUTH_MODE=dev)."""

    @staticmethod
    def get_response(request: HttpRequest) -> Mock:
        response = Mock()
        response.status_code = 200
        return response

    @override_settings(DEBUG=True)
    @pytest.mark.django_db
    def test_dev_mode_injects_mock_user(self) -> None:
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
        middleware = AuthenticationMiddleware(self.get_response)
        request = Mock()
        request.META = {}
        request.user = None

        with patch.dict("os.environ", {"AUTH_MODE": "dev"}, clear=False):
            middleware.process_request(request)

        assert request.user is not None
        assert request.user.username == "dev_admin"

    @override_settings(DEBUG=True)
    def test_dev_mode_rejects_invalid_identity(self) -> None:
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
        response = Mock()
        response.status_code = 200
        return response

    @override_settings(DEBUG=False)
    @pytest.mark.django_db
    def test_iis_mode_reads_windows_auth_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        middleware = AuthenticationMiddleware(self.get_response)
        monkeypatch.setattr(middleware.identity_resolver, "resolve", lambda _: "DOMAIN\\testuser")

        request = Mock()
        request.META = {"HTTP_X_IIS_WINDOWSAUTHTOKEN": "0x123"}
        request.user = None

        with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
            middleware.process_request(request)

        assert request.user is not None
        assert request.user.username == "DOMAIN\\testuser"

    @override_settings(DEBUG=False)
    def test_iis_mode_missing_windows_auth_token_fails_closed(self) -> None:
        middleware = AuthenticationMiddleware(self.get_response)
        request = Mock()
        request.META = {}
        request.user = None

        with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
            middleware.process_request(request)

        assert request.user is not None
        assert not request.user.is_authenticated

    @override_settings(DEBUG=False)
    @pytest.mark.django_db
    def test_iis_mode_creates_django_user_on_first_request(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        middleware = AuthenticationMiddleware(self.get_response)
        monkeypatch.setattr(middleware.identity_resolver, "resolve", lambda _: "DOMAIN\\newuser")

        request = Mock()
        request.META = {"HTTP_X_IIS_WINDOWSAUTHTOKEN": "0x123"}
        request.user = None

        User.objects.filter(username="DOMAIN\\newuser").delete()

        with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
            middleware.process_request(request)

        assert User.objects.filter(username="DOMAIN\\newuser").exists()

    @override_settings(DEBUG=False)
    @pytest.mark.django_db
    def test_iis_mode_reuses_existing_user(self, monkeypatch: pytest.MonkeyPatch) -> None:
        middleware = AuthenticationMiddleware(self.get_response)
        monkeypatch.setattr(
            middleware.identity_resolver, "resolve", lambda _: "DOMAIN\\existinguser"
        )
        user, _ = User.objects.get_or_create(username="DOMAIN\\existinguser")
        original_pk = user.pk

        request = Mock()
        request.META = {"HTTP_X_IIS_WINDOWSAUTHTOKEN": "0x123"}
        request.user = None

        with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
            middleware.process_request(request)

        assert User.objects.filter(username="DOMAIN\\existinguser", pk=original_pk).exists()

    @override_settings(DEBUG=False)
    def test_iis_mode_invalid_token_resolution_treated_anonymous(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        middleware = AuthenticationMiddleware(self.get_response)
        monkeypatch.setattr(middleware.identity_resolver, "resolve", lambda _: None)
        request = Mock()
        request.META = {"HTTP_X_IIS_WINDOWSAUTHTOKEN": "not-a-valid-token"}
        request.user = None

        with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
            middleware.process_request(request)

        assert request.user is not None
        assert not request.user.is_authenticated

    @override_settings(DEBUG=False)
    def test_iis_mode_invalid_resolved_username_treated_anonymous(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        middleware = AuthenticationMiddleware(self.get_response)
        monkeypatch.setattr(middleware.identity_resolver, "resolve", lambda _: "DOMAIN\\bad/user")
        request = Mock()
        request.META = {"HTTP_X_IIS_WINDOWSAUTHTOKEN": "0x123"}
        request.user = None

        with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
            middleware.process_request(request)

        assert request.user is not None
        assert not request.user.is_authenticated

    @override_settings(DEBUG=False)
    @pytest.mark.django_db
    def test_iis_mode_logs_authentication_success(
        self,
        caplog: pytest.LogCaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(logging.getLogger("api"), "propagate", True)
        middleware = AuthenticationMiddleware(self.get_response)
        monkeypatch.setattr(middleware.identity_resolver, "resolve", lambda _: "DOMAIN\\testuser")

        request = Mock()
        request.path = "/api/user/"
        request.META = {
            "HTTP_X_IIS_WINDOWSAUTHTOKEN": "0x123",
            "REMOTE_ADDR": "198.51.100.2",
            "HTTP_USER_AGENT": "pytest-agent",
        }
        request.user = None

        with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
            with caplog.at_level(logging.INFO, logger="api.middleware.authentication"):
                middleware.process_request(request)

        record = cast(
            Any,
            next(r for r in caplog.records if r.name == "api.middleware.authentication"),
        )
        assert record.event_type == "AUTHENTICATION_SUCCESS"
        assert record.user_identifier == "DOMAIN\\testuser"
        assert record.action_attempted == "authenticate X-IIS-WindowsAuthToken"
        assert record.result == "success"

    @override_settings(DEBUG=False)
    def test_iis_mode_logs_invalid_windows_auth_token(
        self,
        caplog: pytest.LogCaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(logging.getLogger("api"), "propagate", True)
        middleware = AuthenticationMiddleware(self.get_response)
        monkeypatch.setattr(middleware.identity_resolver, "resolve", lambda _: None)

        request = Mock()
        request.path = "/api/user/"
        request.META = {
            "HTTP_X_IIS_WINDOWSAUTHTOKEN": "not-a-valid-token",
            "REMOTE_ADDR": "198.51.100.2",
            "HTTP_USER_AGENT": "pytest-agent",
        }
        request.user = None

        with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
            with caplog.at_level(logging.WARNING, logger="api.middleware.authentication"):
                middleware.process_request(request)

        record = cast(
            Any,
            next(r for r in caplog.records if r.name == "api.middleware.authentication"),
        )
        assert record.event_type == "INPUT_VALIDATION_FAILURE"
        assert record.action_attempted == "resolve X-IIS-WindowsAuthToken"
        assert record.result == "failure"
