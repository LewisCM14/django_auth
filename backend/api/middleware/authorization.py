"""Authorization middleware.

Enforces per-view authorization policy via the ``authz_policy`` attribute
set by the permission decorators in ``api.permissions``:

- ``@authz_public`` — no authentication or roles required
- ``@authz_authenticated`` — IIS authentication required, no role check
- ``@authz_roles(...)`` — IIS authentication required with specific role(s)

Role resolution happens only for role-protected views:

- Dev mode (``AUTH_MODE=dev``): reads ``DEV_USER_ROLE`` from environment
- IIS mode (``AUTH_MODE=iis``): queries LDAP for AD group membership (per-request)

This middleware is responsible only for authentication and role checks implied
by the resolved authorization policy. Presence of the required decorator
families is enforced earlier in the middleware stack by
``DecoratorEnforcementMiddleware``.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable

from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils.decorators import sync_and_async_middleware
from rest_framework.exceptions import AuthenticationFailed

from api.constants import AD_GROUP_TO_ROLE_MAP, ROLE_ADMIN, ROLE_VIEWER
from api.middleware.request_id import request_id_var
from api.permissions import AUTHZ_POLICY_ATTR, AUTHZ_ROLES_ATTR

logger = logging.getLogger(__name__)


@sync_and_async_middleware
class AuthorizationMiddleware:
    """Enforces per-view authorization policies set by decorators.

    Reads the ``authz_policy`` attribute from the resolved view and applies
    the corresponding authentication and role checks.  Views without a
    policy raise ``ImproperlyConfigured`` at request time.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        """Initialize the middleware.

        Args:
            get_response: The next middleware or view in the chain.
        """
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Process the request and response.

        Args:
            request: The HTTP request object.

        Returns:
            The HTTP response from the next middleware or view.
        """
        return self.get_response(request)

    def process_view(
        self,
        request: HttpRequest,
        view_func: Any,
        view_args: list[Any],
        view_kwargs: dict[str, Any],
    ) -> HttpResponse | None:
        """Run authorization checks once the target view is known.

        Reads the ``authz_policy`` attribute and applies the corresponding
        authentication and role-resolution logic.

        Args:
            request: The HTTP request object.
            view_func: The resolved Django view callable.
            view_args: Positional args for the view callable.
            view_kwargs: Keyword args for the view callable.
        """
        del view_args, view_kwargs

        try:
            policy = self._get_view_attr(view_func, AUTHZ_POLICY_ATTR, str)
            if policy is None:
                raise ImproperlyConfigured(
                    "Every view in api.views must declare an authorization policy "
                    "using @authz_public, @authz_authenticated, or @authz_roles(...)."
                )

            if policy == "public":
                return None

            if policy == "authenticated":
                self._ensure_authenticated(request)
                return None

            if policy == "roles":
                self._ensure_authenticated(request)
                username = self._get_authenticated_username(request)
                user_roles = self._get_user_roles(username)
                # Django's User model has no 'roles' attribute; we attach it
                # dynamically so the view can read resolved roles from the request.
                request.user.roles = user_roles  # type: ignore[union-attr]

                required_roles: tuple[str, ...] = (
                    self._get_view_attr(view_func, AUTHZ_ROLES_ATTR, tuple) or ()
                )
                if not required_roles:
                    raise ImproperlyConfigured(
                        "@authz_roles decorator requires at least one role."
                    )

                if not any(role in user_roles for role in required_roles):
                    raise PermissionDenied(
                        "User is not a member of any required application roles."
                    )
                return None

            raise ImproperlyConfigured(f"Unknown authz policy '{policy}'.")
        except AuthenticationFailed as exc:
            logger.warning(
                "authentication failed: %s %s — %s", request.method, request.path, exc
            )
            return JsonResponse(
                {
                    "detail": "Authentication credentials were not provided.",
                    "request_id": request_id_var.get(),
                },
                status=401,
            )
        except PermissionDenied as exc:
            username = getattr(request.user, "username", None) or "anonymous"
            logger.warning(
                "permission denied: %s %s %s — %s",
                username,
                request.method,
                request.path,
                exc,
            )
            return JsonResponse(
                {
                    "detail": "You do not have permission to perform this action.",
                    "request_id": request_id_var.get(),
                },
                status=403,
            )

    def _get_view_attr(self, view_func: Any, attr: str, expected_type: type) -> Any:
        """Read a decorator attribute from a view function or its view_class."""
        direct = getattr(view_func, attr, None)
        if isinstance(direct, expected_type):
            return direct
        view_class = getattr(view_func, "view_class", None)
        class_val = getattr(view_class, attr, None)
        return class_val if isinstance(class_val, expected_type) else None

    def _ensure_authenticated(self, request: HttpRequest) -> None:
        """Ensure request has an authenticated user identity."""
        user = request.user
        if not user or not getattr(user, "is_authenticated", False):
            raise AuthenticationFailed("User not authenticated (no REMOTE_USER).")

    def _get_authenticated_username(self, request: HttpRequest) -> str:
        """Return a validated username from an authenticated request."""
        username = getattr(request.user, "username", None)
        if not isinstance(username, str) or not username:
            raise AuthenticationFailed("Authenticated user has no valid username.")
        return username

    def _get_user_roles(self, username: str) -> list[str]:
        """Resolve application roles for a user.

        In dev mode, reads from ``DEV_USER_ROLE`` environment variable.
        In IIS mode, queries LDAP for AD group membership on every request.
        Results are not cached — AD changes take immediate effect.

        Args:
            username: The username to resolve roles for.

        Returns:
            List of application roles the user belongs to.
        """
        if os.getenv("AUTH_MODE", "iis") == "dev":
            dev_role = os.getenv("DEV_USER_ROLE", "admin").lower()
            return [ROLE_ADMIN] if dev_role == "admin" else [ROLE_VIEWER]

        ad_groups = query_ldap_groups(username)

        return list(
            dict.fromkeys(
                AD_GROUP_TO_ROLE_MAP[g] for g in ad_groups if g in AD_GROUP_TO_ROLE_MAP
            )
        )


def query_ldap_groups(username: str) -> list[str]:
    """Query LDAP for user's group memberships.

    In a real implementation, this would connect to Active Directory via LDAP
    and retrieve the list of groups the user belongs to. For now, this is a
    placeholder that returns an empty list (tests mock this function).

    Args:
        username: The username to query (typically DOMAIN\\username).

    Returns:
        List of LDAP group DNs the user belongs to.
    """
    return []
