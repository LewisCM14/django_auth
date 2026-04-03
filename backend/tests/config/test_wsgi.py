"""Tests for WSGI application module."""

from __future__ import annotations

import importlib
import os
from unittest.mock import Mock, patch


class TestWsgiModule:
    """Tests for WSGI module initialization behavior."""

    def test_sets_default_settings_module_and_creates_application(
        self,
        monkeypatch,
    ) -> None:
        """WSGI module sets DJANGO_SETTINGS_MODULE and initializes application."""
        monkeypatch.delenv("DJANGO_SETTINGS_MODULE", raising=False)
        mock_application = Mock()

        with patch(
            "django.core.wsgi.get_wsgi_application", return_value=mock_application
        ):
            import config.wsgi as wsgi_module

            importlib.reload(wsgi_module)

        assert os.environ["DJANGO_SETTINGS_MODULE"] == "config.settings"
        assert wsgi_module.application is mock_application
