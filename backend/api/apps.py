"""Django app configuration for the API application."""

import os

from django.apps import AppConfig
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class ApiConfig(AppConfig):
    """Configuration for the api app.

    Specifies the default field type for auto-generated primary keys and
    defines app metadata.
    """

    default_auto_field: str = "django.db.models.BigAutoField"
    name: str = "api"

    def ready(self) -> None:
        """Validate configuration at app startup.

        Performs critical security checks:
        - AUTH_MODE=dev is forbidden when DEBUG=False (security guard)
        - Only valid AUTH_MODE values are 'dev' and 'iis'

        Raises:
            ImproperlyConfigured: If AUTH_MODE=dev is set with DEBUG=False,
                or if AUTH_MODE is not 'dev' or 'iis'.
        """
        auth_mode = os.getenv("AUTH_MODE", "iis")

        # Validate AUTH_MODE value
        if auth_mode not in ("dev", "iis"):
            raise ImproperlyConfigured(
                f"Invalid AUTH_MODE='{auth_mode}'. Must be 'dev' or 'iis'."
            )

        # Security guard: dev mode cannot run in production
        if auth_mode == "dev" and not settings.DEBUG:
            raise ImproperlyConfigured(
                "AUTH_MODE=dev cannot be used with DEBUG=False. "
                "Development auth mode is unsafe in production."
            )
