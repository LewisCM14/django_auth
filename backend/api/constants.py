"""Constants and configuration values for the API application.

Includes role definitions, LDAP mappings, and other application-wide constants.
"""
from __future__ import annotations

from typing import Final

# Application roles
ROLE_ADMIN: Final[str] = "app_admin"
"""Application administrator role with full access."""

ROLE_VIEWER: Final[str] = "app_viewer"
"""Application viewer role with read-only access."""

ROLES: Final[tuple[str, ...]] = (ROLE_ADMIN, ROLE_VIEWER)
"""All valid application roles."""

# Map Active Directory groups to application roles
# Keys are AD group names (as returned by LDAP), values are application roles
# In production, these should be configured via environment variables or settings
AD_GROUP_TO_ROLE_MAP: Final[dict[str, str]] = {
    "CN=app-admins,OU=Groups,DC=corp,DC=local": ROLE_ADMIN,
    "CN=app-viewers,OU=Groups,DC=corp,DC=local": ROLE_VIEWER,
}
"""Mapping of Active Directory group DNs to application roles.

This map is used by the authorization middleware to translate AD group
membership (from LDAP queries) into application-level roles. In production,
these groups should match your organization's AD structure.

Example AD group DN format:
    CN=app-admins,OU=Groups,DC=corp,DC=local
    
Where:
    CN = Common Name (group name)
    OU = Organizational Unit
    DC = Domain Component
"""
