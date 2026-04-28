"""Tests for the decorator enforcement middleware.

The ``DecoratorEnforcementMiddleware`` runs before authorization and ensures
every view under ``api.views`` explicitly declares all three decorator families:

- **Authorization:** ``@authz_public``, ``@authz_authenticated``, or ``@authz_roles(...)``
- **Rate limiting:** ``@throttle("rate")`` or ``@throttle_exempt``
- **Cache control:** ``@cache_public``, ``@cache_private``, or ``@cache_disabled``

There are no default permissions, rates, or cache policies — missing any one
raises ``ImproperlyConfigured`` at request time.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Coroutine
from typing import Any, cast
from unittest.mock import Mock

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse

from api.middleware.enforcement import DecoratorEnforcementMiddleware


def _make_fully_decorated_view(
    *,
    module: str = "api.views.sample",
    authz_policy: str = "public",
    throttle_rate: str | None = "30/minute",
    cache_policy: str = "private",
) -> Any:
    """Create a dummy view with all three decorator families applied."""

    class FullView:
        pass

    FullView.__module__ = module
    FullView.authz_policy = authz_policy  # type: ignore[attr-defined]  # Test dynamically attaches decorator metadata attrs not declared on the class type.
    FullView._throttle_rate = throttle_rate  # type: ignore[attr-defined]  # Test dynamically attaches decorator metadata attrs not declared on the class type.
    FullView._cache_policy = cache_policy  # type: ignore[attr-defined]  # Test dynamically attaches decorator metadata attrs not declared on the class type.

    def wrapped_view() -> None:
        return None

    wrapped_view.view_class = FullView  # type: ignore[attr-defined]  # Mirrors Django's as_view() behavior where resolver callables carry a runtime view_class attribute.
    return wrapped_view


class TestDecoratorEnforcement:
    """Tests that middleware enforces all three decorator families."""

    @staticmethod
    def get_response(request: Any) -> Mock:
        """Mock ASGI application for middleware testing."""
        response = Mock()
        response.status_code = 200
        return response

    def test_fully_decorated_view_passes(self) -> None:
        """View with all three decorator families passes enforcement."""
        middleware = DecoratorEnforcementMiddleware(self.get_response)
        request = Mock()
        view_func = _make_fully_decorated_view()

        middleware.process_view(request, view_func, [], {})

    def test_missing_throttle_raises_improperly_configured(self) -> None:
        """View without @throttle or @throttle_exempt raises at request time."""
        middleware = DecoratorEnforcementMiddleware(self.get_response)
        request = Mock()

        class NoThrottleView:
            """View with auth and cache but no throttle decorator."""

            authz_policy = "authenticated"
            _cache_policy = "private"

        NoThrottleView.__module__ = "api.views.sample"

        def wrapped_view() -> None:
            return None

        wrapped_view.view_class = NoThrottleView  # type: ignore[attr-defined]  # Mirrors Django's as_view() behavior where resolver callables carry a runtime view_class attribute.

        with pytest.raises(ImproperlyConfigured, match="@throttle"):
            middleware.process_view(request, wrapped_view, [], {})

    def test_missing_cache_raises_improperly_configured(self) -> None:
        """View without @cache_* decorator raises at request time."""
        middleware = DecoratorEnforcementMiddleware(self.get_response)
        request = Mock()

        class NoCacheView:
            """View with auth and throttle but no cache decorator."""

            authz_policy = "authenticated"
            _throttle_rate = "30/minute"

        NoCacheView.__module__ = "api.views.sample"

        def wrapped_view() -> None:
            return None

        wrapped_view.view_class = NoCacheView  # type: ignore[attr-defined]  # Mirrors Django's as_view() behavior where resolver callables carry a runtime view_class attribute.

        with pytest.raises(ImproperlyConfigured, match="@cache_"):
            middleware.process_view(request, wrapped_view, [], {})

    def test_missing_auth_raises_improperly_configured(self) -> None:
        """View without @authz_* decorator raises at request time."""
        middleware = DecoratorEnforcementMiddleware(self.get_response)
        request = Mock()

        class NoAuthView:
            """View with throttle and cache but no auth decorator."""

            _throttle_rate = "30/minute"
            _cache_policy = "private"

        NoAuthView.__module__ = "api.views.sample"

        def wrapped_view() -> None:
            return None

        wrapped_view.view_class = NoAuthView  # type: ignore[attr-defined]  # Mirrors Django's as_view() behavior where resolver callables carry a runtime view_class attribute.

        with pytest.raises(ImproperlyConfigured, match="@authz_"):
            middleware.process_view(request, wrapped_view, [], {})

    def test_throttle_exempt_satisfies_enforcement(self) -> None:
        """View with @throttle_exempt (rate=None) passes the throttle check."""
        middleware = DecoratorEnforcementMiddleware(self.get_response)
        request = Mock()
        view_func = _make_fully_decorated_view(throttle_rate=None)

        middleware.process_view(request, view_func, [], {})

    def test_non_project_view_raises_improperly_configured(self) -> None:
        """Views outside api.views are rejected."""
        middleware = DecoratorEnforcementMiddleware(self.get_response)
        request = Mock()

        def wrapped_view() -> None:
            return None

        wrapped_view.__module__ = "third_party.module"  # Test mutates function metadata to simulate a non-project resolved view.

        with pytest.raises(ImproperlyConfigured, match="api.views"):
            middleware.process_view(request, wrapped_view, [], {})

    def test_is_project_view_returns_false_for_none(self) -> None:
        """_is_project_view handles None safely."""
        middleware = DecoratorEnforcementMiddleware(self.get_response)
        assert middleware._is_project_view(None) is False

    def test_has_view_attr_reads_from_function(self) -> None:
        """_has_view_attr finds attributes set directly on the function."""
        middleware = DecoratorEnforcementMiddleware(self.get_response)

        def fbv() -> None:
            return None

        fbv._throttle_rate = "10/minute"  # type: ignore[attr-defined]  # Simulates decorator-injected metadata on a plain function-based view.

        assert middleware._has_view_attr(fbv, "_throttle_rate") is True
        assert middleware._has_view_attr(fbv, "_cache_policy") is False

    def test_has_view_attr_reads_from_view_class(self) -> None:
        """_has_view_attr finds attributes on the view_class fallback."""
        middleware = DecoratorEnforcementMiddleware(self.get_response)

        class SomeView:
            _cache_policy = "private"

        def fbv() -> None:
            return None

        fbv.view_class = SomeView  # type: ignore[attr-defined]  # Mirrors Django's as_view() runtime attachment for helper fallback coverage.

        assert middleware._has_view_attr(fbv, "_cache_policy") is True
        assert middleware._has_view_attr(fbv, "_throttle_rate") is False


class TestDecoratorEnforcementAsyncCompatibility:
    """Async compatibility coverage for decorator enforcement middleware."""

    def test_supports_async_get_response(self) -> None:
        """Decorator enforcement middleware awaits async downstream responses."""

        async def get_response(request: Any) -> HttpResponse:
            return HttpResponse(status=203)

        middleware = DecoratorEnforcementMiddleware(get_response)
        request = Mock()

        response = asyncio.run(middleware.__acall__(request))

        assert response.status_code == 203

    def test_call_returns_coroutine_in_async_mode(self) -> None:
        """Decorator enforcement middleware __call__ uses async path."""

        async def get_response(request: Any) -> HttpResponse:
            return HttpResponse(status=207)

        middleware = DecoratorEnforcementMiddleware(get_response)
        request = Mock()

        result = middleware(request)
        assert inspect.isawaitable(result)
        response = asyncio.run(cast(Coroutine[Any, Any, HttpResponse], result))

        assert response.status_code == 207
