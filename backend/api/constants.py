"""Constants and configuration values for the API application.

Includes role definitions, LDAP mappings, and other application-wide constants.
"""

from __future__ import annotations

import os
from typing import Final

from django.core.exceptions import ImproperlyConfigured

from api.validation import validate_distinguished_name

# Application roles
ROLE_ADMIN: Final[str] = "app_admin"
"""Application administrator role with full access."""

ROLE_VIEWER: Final[str] = "app_viewer"
"""Application viewer role with read-only access."""

ROLES: Final[tuple[str, ...]] = (ROLE_ADMIN, ROLE_VIEWER)
"""All valid application roles."""


def _required_env(name: str) -> str:
    """Return a required environment variable or fail fast."""

    value = os.getenv(name, "").strip()
    if not value:
        raise ImproperlyConfigured(
            f"{name} is required. Set it in the active deployment .env file."
        )
    return value


ADMIN_AD_GROUP: Final[str] = validate_distinguished_name(
    _required_env("ADMIN_AD_GROUP"), field_name="ADMIN_AD_GROUP"
)
VIEWER_AD_GROUP: Final[str] = validate_distinguished_name(
    _required_env("VIEWER_AD_GROUP"), field_name="VIEWER_AD_GROUP"
)

if ADMIN_AD_GROUP == VIEWER_AD_GROUP:
    raise ImproperlyConfigured(
        "ADMIN_AD_GROUP and VIEWER_AD_GROUP must reference different AD groups."
    )

AD_GROUP_TO_ROLE_MAP: Final[dict[str, str]] = {
    ADMIN_AD_GROUP: ROLE_ADMIN,
    VIEWER_AD_GROUP: ROLE_VIEWER,
}
"""Mapping of Active Directory group DNs to application roles.

The mapping is loaded from environment variables so deployment-specific .env
files can control which AD groups grant each application role.
"""
