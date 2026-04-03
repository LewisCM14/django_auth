"""HTTP cache-control decorators for class-based and function-based views.

Provides explicit per-view cache policy decorators that attach metadata and
apply ``Cache-Control`` response headers.  Every view must declare one of:

- ``@cache_public(max_age=N)`` — cacheable by proxies and browsers
- ``@cache_private`` — browser-only, revalidate each request
- ``@cache_disabled`` — not cacheable at all (``no-store``)

The decorator sets a ``_cache_policy`` attribute on the view so the
decorator enforcement middleware can enforce that every view declares a
policy.
"""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from django.http import HttpRequest, HttpResponseBase
from django.utils.cache import patch_cache_control
from django.views import View

CACHE_POLICY_ATTR = "_cache_policy"


def cache_public(*, max_age: int) -> Callable[[Any], Any]:
    """Mark a view with public cache headers.

    Allows intermediate proxies and the browser to cache the response.

    Args:
        max_age: Maximum cache lifetime in seconds.

    Returns:
        Decorator that applies public cache headers to the target.

    Example::

        @cache_public(max_age=5)
        class HealthView(APIView):
            ...
    """

    def decorator(target: Any) -> Any:
        """Apply public cache policy to a class-based view or callable."""
        if isinstance(target, type) and issubclass(target, View):
            setattr(target, CACHE_POLICY_ATTR, "public")
            _apply_cache_headers_class(target, public=True, max_age=max_age)
            return target
        if callable(target):
            setattr(target, CACHE_POLICY_ATTR, "public")
            return _apply_cache_headers_callable(target, public=True, max_age=max_age)
        msg = f"@cache_public can only decorate View classes or callables, got {type(target)}"
        raise TypeError(msg)

    return decorator


def cache_private(target: Any) -> Any:
    """Mark a view with private, no-cache Cache-Control headers.

    The browser may store the response but must revalidate on every request.
    Appropriate for authenticated, user-specific data.

    Args:
        target: View class or callable to decorate.

    Returns:
        The same object with cache policy metadata and headers applied.
    """
    if isinstance(target, type) and issubclass(target, View):
        setattr(target, CACHE_POLICY_ATTR, "private")
        _apply_cache_headers_class(target, private=True, no_cache=True)
        return target
    if callable(target):
        setattr(target, CACHE_POLICY_ATTR, "private")
        return _apply_cache_headers_callable(target, private=True, no_cache=True)
    msg = f"@cache_private can only decorate View classes or callables, got {type(target)}"
    raise TypeError(msg)


def cache_disabled(target: Any) -> Any:
    """Mark a view with no-store Cache-Control headers.

    Neither proxies nor the browser should cache the response.
    Appropriate for write endpoints and dynamic content.

    Args:
        target: View class or callable to decorate.

    Returns:
        The same object with cache policy metadata and headers applied.
    """
    if isinstance(target, type) and issubclass(target, View):
        setattr(target, CACHE_POLICY_ATTR, "disabled")
        _apply_cache_headers_class(target, no_store=True)
        return target
    if callable(target):
        setattr(target, CACHE_POLICY_ATTR, "disabled")
        return _apply_cache_headers_callable(target, no_store=True)
    msg = f"@cache_disabled can only decorate View classes or callables, got {type(target)}"
    raise TypeError(msg)


def _apply_cache_headers_class(cls: type[View], **cache_kwargs: Any) -> None:
    """Wrap a class-based view's ``dispatch`` to add Cache-Control headers."""
    original_dispatch = cls.dispatch

    @wraps(original_dispatch)
    def dispatch_with_cache(
        self: View,
        request: HttpRequest,
        *args: Any,
        **kwargs: Any,
    ) -> HttpResponseBase:
        """Dispatch and patch Cache-Control headers on the response."""
        response = original_dispatch(self, request, *args, **kwargs)
        patch_cache_control(response, **cache_kwargs)
        return response

    setattr(cls, "dispatch", dispatch_with_cache)


def _apply_cache_headers_callable(
    func: Callable[..., Any], **cache_kwargs: Any
) -> Callable[..., Any]:
    """Wrap a function-based view to add Cache-Control headers."""

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        """Call the wrapped function and patch Cache-Control on the response."""
        response = func(*args, **kwargs)
        if isinstance(response, HttpResponseBase):
            patch_cache_control(response, **cache_kwargs)
        return response

    return wrapper
