"""Tests for Content-Security-Policy middleware behavior."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Coroutine
from typing import Any, cast
from unittest.mock import Mock

from django.http import HttpResponse

from api.middleware.content_security_policy import ContentSecurityPolicyMiddleware


class TestContentSecurityPolicyMiddlewareAsyncCompatibility:
    """Async compatibility coverage for CSP middleware."""

    def test_supports_async_get_response(self) -> None:
        """CSP middleware appends the header for async downstream responses."""

        async def get_response(request: Any) -> HttpResponse:
            return HttpResponse(status=200)

        middleware = ContentSecurityPolicyMiddleware(get_response)
        request = Mock()

        response = asyncio.run(middleware.__acall__(request))

        assert response.status_code == 200
        assert "Content-Security-Policy" in response.headers

    def test_call_returns_coroutine_in_async_mode(self) -> None:
        """CSP middleware __call__ uses async path and adds header."""

        async def get_response(request: Any) -> HttpResponse:
            return HttpResponse(status=208)

        middleware = ContentSecurityPolicyMiddleware(get_response)
        request = Mock()

        result = middleware(request)
        assert inspect.isawaitable(result)
        response = asyncio.run(cast(Coroutine[Any, Any, HttpResponse], result))

        assert response.status_code == 208
        assert "Content-Security-Policy" in response.headers
