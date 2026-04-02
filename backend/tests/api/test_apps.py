"""Tests for the API app configuration."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from api.apps import ApiConfig


class TestApiAppConfig:
    """Tests for the API app configuration and startup checks."""

    def test_dev_mode_allowed_when_debug_true(self) -> None:
        """Development mode (AUTH_MODE=dev) is allowed when DEBUG=True.

        The security guard should not raise an error when both conditions are met:
        - AUTH_MODE=dev (development mode)
        - DEBUG=True (development environment)

        This allows developers to work locally with mocked auth.
        """
        app_config = ApiConfig("api", __import__("api"))

        with override_settings(DEBUG=True):
            with patch.dict("os.environ", {"AUTH_MODE": "dev"}):
                # Should not raise
                app_config.ready()

    def test_dev_mode_raises_when_debug_false(self) -> None:
        """Development mode (AUTH_MODE=dev) is forbidden when DEBUG=False.

        This is a critical security guard: development mode must never be enabled
        in production. If AUTH_MODE=dev is set while DEBUG=False, the application
        refuses to start.
        """
        app_config = ApiConfig("api", __import__("api"))

        with override_settings(DEBUG=False):
            with patch.dict("os.environ", {"AUTH_MODE": "dev"}):
                with pytest.raises(
                    ImproperlyConfigured, match="AUTH_MODE=dev.*DEBUG=False"
                ):
                    app_config.ready()

    def test_iis_mode_allowed_when_debug_false(self) -> None:
        """IIS production mode (AUTH_MODE=iis) is allowed when DEBUG=False.

        In production, AUTH_MODE=iis should work with DEBUG=False without error.
        This is the normal production configuration.
        """
        app_config = ApiConfig("api", __import__("api"))

        with override_settings(DEBUG=False):
            with patch.dict("os.environ", {"AUTH_MODE": "iis"}):
                # Should not raise
                app_config.ready()

    def test_invalid_auth_mode_raises(self) -> None:
        """Invalid AUTH_MODE value raises ImproperlyConfigured.

        Only 'dev' and 'iis' are valid values. Any other value indicates
        misconfiguration and should fail fast.
        """
        app_config = ApiConfig("api", __import__("api"))

        with override_settings(DEBUG=False):
            with patch.dict("os.environ", {"AUTH_MODE": "invalid"}):
                with pytest.raises(ImproperlyConfigured, match="AUTH_MODE.*dev.*iis"):
                    app_config.ready()
