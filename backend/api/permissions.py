"""DRF permission classes for role-based access control.

Provides permission classes for enforcing role-based access control (RBAC)
on API endpoints. Roles are attached to the request.user object by the
authorization middleware.
"""
from __future__ import annotations

from typing import Any

from rest_framework.permissions import BasePermission
from rest_framework.request import Request


class HasAnyRole(BasePermission):
    """Permission: user must have any of the required roles.
    
    For views that allow multiple roles (e.g., admin OR viewer).
    Subclasses should define the `required_roles` attribute as a list of strings.
    """

    required_roles: list[str] = []

    def has_permission(self, request: Request, view: Any) -> bool:
        """Check if user has any of the required roles.
        
        Args:
            request: The HTTP request object.
            view: The view being accessed.
        
        Returns:
            True if user has any required role, False otherwise.
        """
        if not self.required_roles:
            return True
        user_roles: list[str] = getattr(request.user, "roles", [])
        return any(role in user_roles for role in self.required_roles)


class IsAppAdmin(BasePermission):
    """Permission: user must have app_admin role."""

    def has_permission(self, request: Request, view: Any) -> bool:
        """Check if user has app_admin role.
        
        Args:
            request: The HTTP request object.
            view: The view being accessed.
        
        Returns:
            True if user has app_admin role, False otherwise.
        """
        user_roles: list[str] = getattr(request.user, "roles", [])
        return "app_admin" in user_roles


class IsAppViewer(BasePermission):
    """Permission: user must have app_viewer role."""

    def has_permission(self, request: Request, view: Any) -> bool:
        """Check if user has app_viewer role.
        
        Args:
            request: The HTTP request object.
            view: The view being accessed.
        
        Returns:
            True if user has app_viewer role, False otherwise.
        """
        user_roles: list[str] = getattr(request.user, "roles", [])
        return "app_viewer" in user_roles


class IsAdminOrViewer(HasAnyRole):
    """Permission: user must have app_admin OR app_viewer role."""

    required_roles = ["app_admin", "app_viewer"]
