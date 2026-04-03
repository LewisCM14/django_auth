"""Rate-limiting utilities for DRF and Django views.

Provides a ``@throttle`` decorator that applies per-view, per-user rate
limiting with an explicit rate string.  The rate is declared at the view
level rather than in centralised settings or environment variables.

Use ``@throttle_exempt`` to explicitly mark a view as exempt from rate
limiting.  Every view must declare one or the other — the decorator
enforcement middleware enforces this.
"""

from __future__ import annotations

import math
from functools import wraps
from typing import Any, Callable, cast

from django.http import HttpRequest, HttpResponseBase, JsonResponse
from django.views import View
from rest_framework.exceptions import Throttled
from rest_framework.request import Request
from rest_framework.throttling import SimpleRateThrottle

from api.middleware.request_id import request_id_var

THROTTLE_RATE_ATTR = "_throttle_rate"


class RemoteUserRateThrottle(SimpleRateThrottle):
    """Per-view rate throttle keyed on authenticated REMOTE_USER identity.

    This project authenticates users in middleware rather than via DRF's
    authentication system.  The cache key is derived from ``request.user``
    when authenticated, falling back to IP for unauthenticated requests.

    The throttle rate is read from the view's ``_throttle_rate`` attribute,
    which is set by the ``@throttle`` decorator.
    """

    def __init__(self) -> None:
        """Skip default rate parsing; rate is resolved per-request."""

    def allow_request(self, request: HttpRequest, view: Any) -> bool:
        """Check rate limit using the view's ``_throttle_rate`` attribute.

        Args:
            request: Incoming HTTP request.
            view: Resolved view instance.

        Returns:
            ``True`` if the request is allowed, ``False`` if throttled.
        """
        rate: str | None = getattr(view, "_throttle_rate", None)
        if rate is None:
            return True
        self.rate = rate
        self.num_requests, self.duration = self.parse_rate(rate)
        self.scope = type(view).__name__
        return super().allow_request(cast(Request, request), view)

    def get_cache_key(self, request: Request, view: Any) -> str | None:
        """Build cache key using REMOTE_USER identity or client IP.

        Args:
            request: Incoming HTTP request.
            view: Resolved view instance.

        Returns:
            Cache key string.
        """
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            ident = user.get_username()
        else:
            ident = self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}


def throttle(rate: str) -> Callable[[Any], Any]:
    """Apply per-view rate limiting with an explicit rate string.

    Can decorate DRF ``APIView`` classes, Django ``View`` classes, or
    plain function-based views.

    Args:
        rate: DRF rate string (e.g. ``"60/minute"``, ``"10/hour"``).

    Returns:
        Decorator that applies rate limiting to the target.

    Example::

        @throttle("60/minute")
        @authz_public
        class HealthView(APIView):
            ...

        @throttle("30/minute")
        def my_function_view(request):
            ...
    """

    def decorator(target: Any) -> Any:
        """Apply throttle to a class-based view or callable."""
        if isinstance(target, type) and issubclass(target, View):
            return _throttle_class(target, rate)
        if callable(target):
            return _throttle_callable(target, rate)
        msg = (
            f"@throttle can only decorate View classes or callables, got {type(target)}"
        )
        raise TypeError(msg)

    return decorator


def throttle_exempt(target: Any) -> Any:
    """Mark a view as explicitly exempt from rate limiting.

    Sets ``_throttle_rate`` to ``None`` so the enforcement middleware
    recognizes the attribute as present (policy declared) while
    ``RemoteUserRateThrottle.allow_request`` passes all requests through.

    Args:
        target: View class or callable to exempt.

    Returns:
        The same object with throttle rate metadata set to ``None``.
    """
    setattr(target, THROTTLE_RATE_ATTR, None)
    return target


def _throttle_class(cls: type[View], rate: str) -> type[View]:
    """Apply throttle to a class-based view.

    For DRF ``APIView`` subclasses, sets ``throttle_classes`` so DRF's
    built-in throttle machinery activates.  For plain Django ``View``
    subclasses, wraps ``dispatch`` with a manual throttle check.
    """
    cls._throttle_rate = rate  # type: ignore[attr-defined]  # decorator injects attr not declared on View stubs

    # DRF APIView: use DRF's built-in throttle machinery.
    if hasattr(cls, "throttle_classes"):
        cls.throttle_classes = [RemoteUserRateThrottle]
        return cls

    # Django View: wrap dispatch with manual throttle check.
    original_dispatch = cls.dispatch

    @wraps(original_dispatch)
    def dispatch_with_throttle(
        self: View,
        request: HttpRequest,
        *args: Any,
        **kwargs: Any,
    ) -> HttpResponseBase:
        """Evaluate throttle before dispatching to the underlying view."""
        throttle_instance = RemoteUserRateThrottle()
        if not throttle_instance.allow_request(request, self):
            wait_seconds = _throttle_wait_seconds(throttle_instance)
            detail = _throttle_detail(wait_seconds)
            request_id = getattr(request, "request_id", request_id_var.get())
            response = JsonResponse(
                {"detail": detail, "request_id": request_id},
                status=429,
            )
            if wait_seconds is not None:
                response["Retry-After"] = str(wait_seconds)
            return response
        return original_dispatch(self, request, *args, **kwargs)

    setattr(cls, "dispatch", dispatch_with_throttle)
    return cls


def _throttle_callable(func: Callable[..., Any], rate: str) -> Callable[..., Any]:
    """Apply throttle to a function-based view or view method."""

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        """Evaluate throttle before calling the wrapped function."""
        request: HttpRequest | None = None
        for arg in args:
            if isinstance(arg, HttpRequest):
                request = arg
                break

        if request is None:
            return func(*args, **kwargs)

        throttle_instance = RemoteUserRateThrottle()
        # Build a lightweight stub so the throttle can read the rate and
        # derive a unique cache-key scope from the function name.
        stub = type(func.__qualname__, (), {"_throttle_rate": rate})()
        if not throttle_instance.allow_request(request, stub):
            wait_seconds = _throttle_wait_seconds(throttle_instance)
            detail = _throttle_detail(wait_seconds)
            request_id = getattr(request, "request_id", request_id_var.get())
            response = JsonResponse(
                {"detail": detail, "request_id": request_id},
                status=429,
            )
            if wait_seconds is not None:
                response["Retry-After"] = str(wait_seconds)
            return response

        return func(*args, **kwargs)

    wrapper._throttle_rate = rate  # type: ignore[attr-defined]  # decorator injects attr not expressible on Callable type
    return wrapper


def _throttle_wait_seconds(throttle_instance: SimpleRateThrottle) -> int | None:
    """Return Retry-After value in seconds for a denied throttle request."""
    wait = throttle_instance.wait()
    if wait is None:
        return None
    return max(0, math.ceil(wait))


def _throttle_detail(wait_seconds: int | None) -> str:
    """Build DRF-consistent throttle error detail string."""
    if wait_seconds is None:
        return str(Throttled().detail)
    return str(Throttled(wait=wait_seconds).detail)
