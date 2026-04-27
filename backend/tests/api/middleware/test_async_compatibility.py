"""Async compatibility tests for custom middleware classes."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Coroutine
from typing import Any, cast
from unittest.mock import Mock, patch

import pytest
from django.http import HttpResponse

from api.middleware.authentication import AuthenticationMiddleware
from api.middleware.authorization import AuthorizationMiddleware
from api.middleware.content_security_policy import ContentSecurityPolicyMiddleware
from api.middleware.enforcement import DecoratorEnforcementMiddleware


@pytest.mark.django_db
def test_authentication_middleware_supports_async_get_response() -> None:
    """Authentication middleware handles async chains without returning bare coroutines."""

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


def test_authorization_middleware_supports_async_get_response() -> None:
    """Authorization middleware awaits async downstream responses."""

    async def get_response(request: Any) -> HttpResponse:
        return HttpResponse(status=202)

    middleware = AuthorizationMiddleware(get_response)
    request = Mock()

    response = asyncio.run(middleware.__acall__(request))

    assert response.status_code == 202


def test_enforcement_middleware_supports_async_get_response() -> None:
    """Decorator enforcement middleware awaits async downstream responses."""

    async def get_response(request: Any) -> HttpResponse:
        return HttpResponse(status=203)

    middleware = DecoratorEnforcementMiddleware(get_response)
    request = Mock()

    response = asyncio.run(middleware.__acall__(request))

    assert response.status_code == 203


def test_csp_middleware_supports_async_get_response() -> None:
    """CSP middleware appends the CSP header for async downstream responses."""

    async def get_response(request: Any) -> HttpResponse:
        return HttpResponse(status=200)

    middleware = ContentSecurityPolicyMiddleware(get_response)
    request = Mock()

    response = asyncio.run(middleware.__acall__(request))

    assert response.status_code == 200
    assert "Content-Security-Policy" in response.headers


@pytest.mark.django_db
def test_authentication_middleware_call_returns_coroutine_in_async_mode() -> None:
    """__call__ returns a coroutine when wired into an async middleware chain."""

    async def get_response(request: Any) -> HttpResponse:
        return HttpResponse(status=205)

    middleware = AuthenticationMiddleware(get_response)
    request = Mock()
    request.META = {}
    request.user = None

    with patch.dict(
        "os.environ", {"AUTH_MODE": "dev", "DEV_USER_IDENTITY": "dev_async_call_user"}
    ):
        result = middleware(request)
        assert inspect.isawaitable(result)
        response = asyncio.run(cast(Coroutine[Any, Any, HttpResponse], result))

    assert response.status_code == 205
    assert request.user is not None
    assert request.user.username == "dev_async_call_user"


def test_authorization_middleware_call_returns_coroutine_in_async_mode() -> None:
    """Authorization middleware __call__ uses the async path when required."""

    async def get_response(request: Any) -> HttpResponse:
        return HttpResponse(status=206)

    middleware = AuthorizationMiddleware(get_response)
    request = Mock()

    result = middleware(request)
    assert inspect.isawaitable(result)
    response = asyncio.run(cast(Coroutine[Any, Any, HttpResponse], result))

    assert response.status_code == 206


def test_enforcement_middleware_call_returns_coroutine_in_async_mode() -> None:
    """Decorator enforcement middleware __call__ uses the async path."""

    async def get_response(request: Any) -> HttpResponse:
        return HttpResponse(status=207)

    middleware = DecoratorEnforcementMiddleware(get_response)
    request = Mock()

    result = middleware(request)
    assert inspect.isawaitable(result)
    response = asyncio.run(cast(Coroutine[Any, Any, HttpResponse], result))

    assert response.status_code == 207


def test_csp_middleware_call_returns_coroutine_in_async_mode() -> None:
    """CSP middleware __call__ uses async path and still adds the header."""

    async def get_response(request: Any) -> HttpResponse:
        return HttpResponse(status=208)

    middleware = ContentSecurityPolicyMiddleware(get_response)
    request = Mock()

    result = middleware(request)
    assert inspect.isawaitable(result)
    response = asyncio.run(cast(Coroutine[Any, Any, HttpResponse], result))

    assert response.status_code == 208
    assert "Content-Security-Policy" in response.headers
