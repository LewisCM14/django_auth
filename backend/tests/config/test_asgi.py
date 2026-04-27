"""Tests for ASGI application module."""

from __future__ import annotations

import importlib
import os
from unittest.mock import Mock, patch

import pytest
from django.test import override_settings


class TestAsgiModule:
    """Tests for ASGI module initialization behavior."""

    def test_sets_default_settings_module_and_creates_application(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """ASGI module sets DJANGO_SETTINGS_MODULE and initializes application."""
        monkeypatch.delenv("DJANGO_SETTINGS_MODULE", raising=False)
        mock_application = Mock(name="django_asgi_app")
        wrapped_application = Mock(name="wrapped_staticfiles_app")

        with override_settings(DEBUG=True):
            with (
                patch(
                    "django.core.asgi.get_asgi_application",
                    return_value=mock_application,
                ),
                patch(
                    "django.contrib.staticfiles.handlers.ASGIStaticFilesHandler",
                    return_value=wrapped_application,
                ),
            ):
                import config.asgi as asgi_module

                importlib.reload(asgi_module)

        assert os.environ["DJANGO_SETTINGS_MODULE"] == "config.settings"
        assert asgi_module.django_asgi_app is mock_application
        assert asgi_module.application is wrapped_application
