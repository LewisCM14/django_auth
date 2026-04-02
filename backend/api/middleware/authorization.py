"""Authorization middleware.

Enforces explicit per-view authorization policy via decorators.
Every view under ``api.views`` must declare one of:

- ``@authz_public`` — no authentication or roles required
- ``@authz_authenticated`` — IIS authentication required, no role check
- ``@authz_roles(...)`` — IIS authentication required with specific role(s)

Role resolution happens only for role-protected views:

- Dev mode (``AUTH_MODE=dev``): reads ``DEV_USER_ROLE`` from environment
- IIS mode (``AUTH_MODE=iis``): queries LDAP for AD group membership (cached)
"""

from __future__ import annotations

import os
from typing import Any, Callable

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils.decorators import sync_and_async_middleware
from rest_framework.exceptions import AuthenticationFailed

from api.constants import AD_GROUP_TO_ROLE_MAP, ROLE_ADMIN, ROLE_VIEWER
from api.permissions import AUTHZ_POLICY_ATTR, AUTHZ_ROLES_ATTR


@sync_and_async_middleware
class AuthorizationMiddleware:
    """Enforces per-view authorization policies set by decorators.

    Strict mode: all routed views must live under ``api.views`` and declare
    an explicit authorization policy. Views without a policy raise
    ``ImproperlyConfigured`` at request time.
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

        Strict mode is enabled: only views under ``api.views`` are allowed and
        every such view must explicitly declare one auth policy decorator.

        Args:
            request: The HTTP request object.
            view_func: The resolved Django view callable.
            view_args: Positional args for the view callable.
            view_kwargs: Keyword args for the view callable.
        """
        del view_args, view_kwargs

        if not self._is_project_view(view_func):
            raise ImproperlyConfigured(
                "All routed views must live under api.views and declare an "
                "authorization policy decorator. Route third-party endpoints "
                "through wrapper views in api.views."
            )

        try:
            policy = self._get_view_policy(view_func)
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
                request.user.roles = user_roles  # type: ignore[union-attr]

                required_roles = self._get_required_roles(view_func)
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
        except AuthenticationFailed:
            return JsonResponse(
                {"detail": "Authentication credentials were not provided."},
                status=401,
            )
        except PermissionDenied:
            return JsonResponse(
                {"detail": "You do not have permission to perform this action."},
                status=403,
            )

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

    def _get_view_policy(self, view_func: Any) -> str | None:
        """Get authorization policy from function-based or class-based view."""
        direct_policy = getattr(view_func, AUTHZ_POLICY_ATTR, None)
        if isinstance(direct_policy, str):
            return direct_policy

        view_class = getattr(view_func, "view_class", None)
        class_policy = getattr(view_class, AUTHZ_POLICY_ATTR, None)
        if isinstance(class_policy, str):
            return class_policy

        return None

    def _get_required_roles(self, view_func: Any) -> tuple[str, ...]:
        """Return required roles from @authz_roles decorator metadata."""
        direct_roles = getattr(view_func, AUTHZ_ROLES_ATTR, None)
        if isinstance(direct_roles, tuple):
            return direct_roles

        view_class = getattr(view_func, "view_class", None)
        class_roles = getattr(view_class, AUTHZ_ROLES_ATTR, None)
        if isinstance(class_roles, tuple):
            return class_roles

        return ()

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
        In IIS mode, queries LDAP for AD group membership (with caching).

        Args:
            username: The username to resolve roles for.

        Returns:
            List of application roles the user belongs to.
        """
        if os.getenv("AUTH_MODE", "iis") == "dev":
            dev_role = os.getenv("DEV_USER_ROLE", "admin").lower()
            return [ROLE_ADMIN] if dev_role == "admin" else [ROLE_VIEWER]

        cache_key = f"ldap_groups_{username}"

        cached_roles = cache.get(cache_key)
        if cached_roles is not None:
            return cached_roles  # type: ignore[no-any-return]

        ad_groups = query_ldap_groups(username)

        roles = []
        for ad_group in ad_groups:
            if ad_group in AD_GROUP_TO_ROLE_MAP:
                role = AD_GROUP_TO_ROLE_MAP[ad_group]
                if role not in roles:
                    roles.append(role)

        cache_ttl = getattr(settings, "LDAP_CACHE_TTL", 300)
        cache.set(cache_key, roles, cache_ttl)

        return roles


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
