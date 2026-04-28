"""Decorator enforcement middleware.

Ensures every view under ``api.views`` explicitly declares all three
required decorator families:

- **Authorization:** ``@authz_public``, ``@authz_authenticated``, or ``@authz_roles(...)``
- **Rate limiting:** ``@throttle("rate")`` or ``@throttle_exempt``
- **Cache control:** ``@cache_public``, ``@cache_private``, or ``@cache_disabled``

This middleware runs *before* ``AuthorizationMiddleware`` so that
misconfigured views are caught before any authentication or LDAP work
takes place.  Missing any decorator raises ``ImproperlyConfigured``.
"""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Any, Callable, cast

from asgiref.sync import iscoroutinefunction, markcoroutinefunction
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpRequest, HttpResponse

from api.caching import CACHE_POLICY_ATTR
from api.permissions import AUTHZ_POLICY_ATTR
from api.throttling import THROTTLE_RATE_ATTR

REQUIRED_VIEW_ATTRS: tuple[tuple[str, str], ...] = (
    (
        THROTTLE_RATE_ATTR,
        "Every view in api.views must declare a rate limit using "
        "@throttle('rate') or @throttle_exempt.",
    ),
    (
        CACHE_POLICY_ATTR,
        "Every view in api.views must declare a cache policy using "
        "@cache_public, @cache_private, or @cache_disabled.",
    ),
    (
        AUTHZ_POLICY_ATTR,
        "Every view in api.views must declare an authorization policy "
        "using @authz_public, @authz_authenticated, or @authz_roles(...).",
    ),
)


class DecoratorEnforcementMiddleware:
    """Enforce that every project view declares all required decorators.

    Checks for the presence of ``_throttle_rate``, ``_cache_policy``, and
    ``authz_policy`` metadata attributes.  The actual *values* are validated
    by the downstream ``AuthorizationMiddleware``; this middleware only
    verifies that the attributes exist (i.e. the developer remembered to
    apply the decorators).
    """

    def __init__(self, get_response: Callable[[HttpRequest], Any]) -> None:
        """Initialize the middleware.

        Args:
            get_response: The next middleware or view in the chain.
        """
        self.get_response = get_response
        self.is_async = iscoroutinefunction(get_response)
        if self.is_async:
            markcoroutinefunction(self)

    def __call__(self, request: HttpRequest) -> HttpResponse | Awaitable[HttpResponse]:
        """Continue the request through sync or async middleware chains."""
        if self.is_async:
            return self.__acall__(request)
        return cast(HttpResponse, self.get_response(request))

    async def __acall__(self, request: HttpRequest) -> HttpResponse:
        """Continue the request through the async middleware chain."""
        return cast(HttpResponse, await self.get_response(request))

    def process_view(
        self,
        request: HttpRequest,
        view_func: Any,
        view_args: list[Any],
        view_kwargs: dict[str, Any],
    ) -> None:
        """Verify all three decorator families are present on the resolved view.

        Args:
            request: The HTTP request object.
            view_func: The resolved Django view callable.
            view_args: Positional args for the view callable.
            view_kwargs: Keyword args for the view callable.
        """
        del request, view_args, view_kwargs

        if not self._is_project_view(view_func):
            raise ImproperlyConfigured(
                "All routed views must live under api.views and declare "
                "authorization, throttle, and cache decorators. Route "
                "third-party endpoints through wrapper views in api.views."
            )

        for required_attr, error_message in REQUIRED_VIEW_ATTRS:
            if not self._has_view_attr(view_func, required_attr):
                raise ImproperlyConfigured(error_message)

    def _is_project_view(self, view_func: Any | None) -> bool:
        """Return True when the resolved view belongs to api.views."""
        if view_func is None:
            return False

        module_name = getattr(view_func, "__module__", "")
        if isinstance(module_name, str) and module_name.startswith("api.views"):
            return True

        view_class = getattr(view_func, "view_class", None)
        class_module = getattr(view_class, "__module__", "")
        return isinstance(class_module, str) and class_module.startswith("api.views")

    def _has_view_attr(self, view_func: Any, attr: str) -> bool:
        """Return True when *attr* exists on the view or its view_class."""
        if hasattr(view_func, attr):
            return True
        view_class = getattr(view_func, "view_class", None)
        return view_class is not None and hasattr(view_class, attr)
