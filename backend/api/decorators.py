"""Authorization decorators for explicit per-view access policy.

These decorators attach policy metadata to views so authorization middleware
can enforce access consistently and avoid implicit defaults.
"""
from __future__ import annotations

from typing import Any, Callable

AUTHZ_POLICY_ATTR = "authz_policy"
AUTHZ_ROLES_ATTR = "authz_roles"


def authz_public(view_obj: Any) -> Any:
    """Mark a view as public (no authorization checks).

    Args:
        view_obj: Function-based view callable or class-based view class.

    Returns:
        The same object with authorization metadata attached.
    """
    setattr(view_obj, AUTHZ_POLICY_ATTR, "public")
    return view_obj


def authz_authenticated(view_obj: Any) -> Any:
    """Mark a view as accessible to any authenticated user.

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
