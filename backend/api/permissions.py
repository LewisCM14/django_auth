"""Per-view authorization permissions.

Decorators that attach policy metadata to views so the authorization
middleware can enforce access consistently with no implicit defaults.
"""

from __future__ import annotations

from typing import Any, Callable

AUTHZ_POLICY_ATTR = "authz_policy"
AUTHZ_ROLES_ATTR = "authz_roles"


def authz_public(view_obj: Any) -> Any:
    """Mark a view as public (no authentication or authorization).

    Use for endpoints that must be reachable without any credentials,
    e.g. load-balancer health probes.

    Args:
        view_obj: Function-based view callable or class-based view class.

    Returns:
        The same object with authorization metadata attached.
    """
    setattr(view_obj, AUTHZ_POLICY_ATTR, "public")
    return view_obj


def authz_authenticated(view_obj: Any) -> Any:
    """Mark a view as requiring IIS authentication only (no role check).

    Use for endpoints accessible to any domain user who has authenticated
    through IIS, without requiring a specific application role.

    Args:
        view_obj: Function-based view callable or class-based view class.

    Returns:
        The same object with authorization metadata attached.
    """
    setattr(view_obj, AUTHZ_POLICY_ATTR, "authenticated")
    return view_obj


def authz_roles(*roles: str) -> Callable[[Any], Any]:
    """Mark a view as requiring at least one of the provided roles.

    Args:
        *roles: Application role names allowed to access the view.

    Returns:
        Decorator that adds policy and required role metadata.
    """

    def decorator(view_obj: Any) -> Any:
        """Attach role-based authorization metadata to a view object."""
        setattr(view_obj, AUTHZ_POLICY_ATTR, "roles")
        setattr(view_obj, AUTHZ_ROLES_ATTR, tuple(roles))
        return view_obj

    return decorator
