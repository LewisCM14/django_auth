"""Tests for authentication middleware behavior."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Coroutine
from typing import Any, cast
from unittest.mock import Mock, patch

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse
from django.http import HttpRequest
from django.test import override_settings

from api.middleware import authentication
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
        monkeypatch.setattr(type(middleware.identity_resolver), "resolve", lambda _self, _token: "DOMAIN\\testuser")

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
        monkeypatch.setattr(type(middleware.identity_resolver), "resolve", lambda _self, _token: "DOMAIN\\newuser")

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
            type(middleware.identity_resolver), "resolve", lambda _self, _token: "DOMAIN\\existinguser"
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
        monkeypatch.setattr(type(middleware.identity_resolver), "resolve", lambda _self, _token: None)
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
        monkeypatch.setattr(type(middleware.identity_resolver), "resolve", lambda _self, _token: "DOMAIN\\bad/user")
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
        monkeypatch.setattr(type(middleware.identity_resolver), "resolve", lambda _self, _token: "DOMAIN\\testuser")

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
        monkeypatch.setattr(type(middleware.identity_resolver), "resolve", lambda _self, _token: None)

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


class TestWindowsAuthIdentityResolver:
    """Unit tests for Windows auth token resolution helpers."""

    @pytest.mark.parametrize(
        ("token", "expected"),
        [("0x10", 16), ("10", 16), ("", None), ("not-hex", None)],
    )
    def test_parse_token_handle(self, token: str, expected: int | None) -> None:
        assert authentication._parse_token_handle(token) == expected

    def test_load_pywin32_modules_returns_none_on_non_windows(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(authentication.sys, "platform", "linux")
        assert authentication._load_pywin32_modules() is None

    def test_load_pywin32_modules_returns_none_when_packages_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(authentication.sys, "platform", "win32")
        monkeypatch.setattr(authentication.importlib.util, "find_spec", lambda _: None)
        assert authentication._load_pywin32_modules() is None

    def test_load_pywin32_modules_returns_none_when_security_package_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(authentication.sys, "platform", "win32")

        def _find_spec(name: str) -> object | None:
            if name == "win32api":
                return object()
            return None

        monkeypatch.setattr(authentication.importlib.util, "find_spec", _find_spec)
        assert authentication._load_pywin32_modules() is None

    def test_load_pywin32_modules_imports_modules_when_available(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(authentication.sys, "platform", "win32")
        monkeypatch.setattr(
            authentication.importlib.util,
            "find_spec",
            lambda _: object(),
        )
        fake_api = object()
        fake_security = object()

        def _fake_import_module(name: str) -> object:
            if name == "win32api":
                return fake_api
            if name == "win32security":
                return fake_security
            raise AssertionError(f"unexpected module import: {name}")

        monkeypatch.setattr(authentication.importlib, "import_module", _fake_import_module)

        assert authentication._load_pywin32_modules() == (fake_api, fake_security)

    def test_resolve_handles_os_error_during_impersonation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        resolver = authentication.WindowsAuthIdentityResolver()

        class BrokenSecurity:
            def ImpersonateLoggedOnUser(self, handle: int) -> None:
                raise OSError("boom")

            def RevertToSelf(self) -> None:
                raise AssertionError(
                    "should not revert when impersonation never started"
                )

        class FakeApi:
            def __init__(self) -> None:
                self.closed: list[int] = []

            def GetUserName(self) -> str:
                return "DOMAIN\\ignored"

            def CloseHandle(self, handle: int) -> None:
                self.closed.append(handle)

        fake_api = FakeApi()
        monkeypatch.setattr(
            authentication, "_load_pywin32_modules", lambda: (fake_api, BrokenSecurity())
        )

        assert resolver.resolve("0x10") is None
        assert fake_api.closed == [16]

    def test_resolve_success_with_revert_and_close_errors_logged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        resolver = authentication.WindowsAuthIdentityResolver()

        class FakeSecurity:
            def ImpersonateLoggedOnUser(self, handle: int) -> None:
                return None

            def RevertToSelf(self) -> None:
                raise OSError("cannot revert")

        class FakeApi:
            def GetUserName(self) -> str:
                return "DOMAIN\\ok"

            def CloseHandle(self, handle: int) -> None:
                raise OSError("cannot close")

        monkeypatch.setattr(
            authentication, "_load_pywin32_modules", lambda: (FakeApi(), FakeSecurity())
        )
        assert resolver.resolve("0x20") == "DOMAIN\\ok"

    def test_resolve_returns_none_when_modules_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        resolver = authentication.WindowsAuthIdentityResolver()
        monkeypatch.setattr(authentication, "_load_pywin32_modules", lambda: None)
        assert resolver.resolve("0x10") is None

    def test_resolve_returns_none_for_blank_header(self) -> None:
        resolver = authentication.WindowsAuthIdentityResolver()
        assert resolver.resolve("  ") is None


class TestAuthenticationMiddlewareAsyncCompatibility:
    """Async compatibility coverage for authentication middleware."""

    @pytest.mark.django_db
    def test_supports_async_get_response(self) -> None:
        """Authentication middleware handles async chains end-to-end."""

        async def get_response(request: Any) -> HttpResponse:
            return HttpResponse(status=204)

        middleware = AuthenticationMiddleware(get_response)
        request = Mock()
        request.META = {}
        request.user = None

        with patch.dict(
            "os.environ", {"AUTH_MODE": "dev", "DEV_USER_IDENTITY": "dev_async_user"}
        ):
            response = asyncio.run(middleware.__acall__(request))

        assert response.status_code == 204
        assert request.user is not None
        assert request.user.username == "dev_async_user"

    @pytest.mark.django_db
    def test_call_returns_coroutine_in_async_mode(self) -> None:
        """__call__ returns awaitable when middleware is wired into async chain."""

        async def get_response(request: Any) -> HttpResponse:
            return HttpResponse(status=205)

        middleware = AuthenticationMiddleware(get_response)
        request = Mock()
        request.META = {}
        request.user = None

        with patch.dict(
            "os.environ",
            {"AUTH_MODE": "dev", "DEV_USER_IDENTITY": "dev_async_call_user"},
        ):
            result = middleware(request)
            assert inspect.isawaitable(result)
            response = asyncio.run(cast(Coroutine[Any, Any, HttpResponse], result))

        assert response.status_code == 205
        assert request.user is not None
        assert request.user.username == "dev_async_call_user"
