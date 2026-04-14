"""Tests for settings module import-time validation and defaults."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest
from django.core.exceptions import ImproperlyConfigured


SETTINGS_PATH = Path(__file__).resolve().parents[2] / "config" / "settings.py"


def _load_settings_module(module_name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, SETTINGS_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to build import spec for config.settings")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestSettingsImportValidation:
    """Tests for import-time settings validation and defaults."""

    def test_invalid_auth_mode_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Importing settings fails fast when AUTH_MODE is invalid."""
        monkeypatch.setenv("AUTH_MODE", "invalid")
        monkeypatch.setenv("SECRET_KEY", "test-secret")
        monkeypatch.setenv("ALLOWED_HOSTS", "localhost")

        with patch("dotenv.load_dotenv", return_value=True):
            with pytest.raises(ImproperlyConfigured, match="AUTH_MODE must be either"):
                _load_settings_module("test_settings_invalid_auth_mode")

    def test_missing_secret_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Importing settings fails when SECRET_KEY is empty."""
        monkeypatch.setenv("AUTH_MODE", "dev")
        monkeypatch.setenv("SECRET_KEY", "")
        monkeypatch.setenv("ALLOWED_HOSTS", "localhost")

        with patch("dotenv.load_dotenv", return_value=True):
            with pytest.raises(ImproperlyConfigured, match="SECRET_KEY is required"):
                _load_settings_module("test_settings_missing_secret")

    def test_allowed_hosts_defaults_when_unset(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ALLOWED_HOSTS falls back to localhost defaults when not configured."""
        monkeypatch.setenv("AUTH_MODE", "dev")
        monkeypatch.setenv("SECRET_KEY", "test-secret")
        monkeypatch.setenv("ALLOWED_HOSTS", "")

        with patch("dotenv.load_dotenv", return_value=True):
            module = _load_settings_module("test_settings_allowed_hosts_default")

        assert module.ALLOWED_HOSTS == ["localhost", "127.0.0.1"]


class TestSettingsLoggingConfig:
    """Tests for LOGGING configuration exported by settings."""

    def test_logging_config_has_request_id_filter(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """LOGGING dict exposes the request_id filter for handler attachment."""
        monkeypatch.setenv("AUTH_MODE", "dev")
        monkeypatch.setenv("SECRET_KEY", "test-secret")

        with patch("dotenv.load_dotenv", return_value=True):
            module = _load_settings_module("test_settings_logging_filter")

        assert "request_id" in module.LOGGING["filters"]

    def test_logging_config_console_handler_exists(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """LOGGING dict includes a console handler wired to stderr."""
        monkeypatch.setenv("AUTH_MODE", "dev")
        monkeypatch.setenv("SECRET_KEY", "test-secret")

        with patch("dotenv.load_dotenv", return_value=True):
            module = _load_settings_module("test_settings_logging_console")

        handler = module.LOGGING["handlers"]["console"]
        assert handler["class"] == "logging.StreamHandler"
        assert handler["stream"] == "ext://sys.stderr"
        assert "request_id" in handler["filters"]


class TestSettingsCacheConfig:
    """Tests for cache backend configuration exported by settings."""

    def test_default_cache_backend_is_locmem(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CACHES is configured for LocMemCache by default."""
        monkeypatch.setenv("AUTH_MODE", "dev")
        monkeypatch.setenv("SECRET_KEY", "test-secret")

        with patch("dotenv.load_dotenv", return_value=True):
            module = _load_settings_module("test_settings_default_cache_locmem")

        assert module.CACHES["default"]["BACKEND"] == (
            "django.core.cache.backends.locmem.LocMemCache"
        )


class TestSettingsVersionConfig:
    """Tests for API version configuration exported by settings."""

    def test_api_version_defaults_to_placeholder_when_unset(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """API_VERSION defaults to the APP_VERSION placeholder."""
        monkeypatch.setenv("AUTH_MODE", "dev")
        monkeypatch.setenv("SECRET_KEY", "test-secret")
        monkeypatch.delenv("API_VERSION", raising=False)

        with patch("dotenv.load_dotenv", return_value=True):
            module = _load_settings_module("test_settings_api_version_default")

        assert module.API_VERSION == "APP_VERSION"
        assert module.SPECTACULAR_SETTINGS["VERSION"] == "APP_VERSION"

    def test_api_version_is_loaded_and_reused_by_docs(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """API_VERSION is loaded from env and reused by SPECTACULAR_SETTINGS."""
        monkeypatch.setenv("AUTH_MODE", "dev")
        monkeypatch.setenv("SECRET_KEY", "test-secret")
        monkeypatch.setenv("API_VERSION", "2026.04.07")

        with patch("dotenv.load_dotenv", return_value=True):
            module = _load_settings_module("test_settings_api_version")

        assert module.API_VERSION == "2026.04.07"
        assert module.SPECTACULAR_SETTINGS["VERSION"] == "2026.04.07"

    def test_swagger_ui_uses_sidecar_assets(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Swagger UI settings point at bundled sidecar assets for offline use."""
        monkeypatch.setenv("AUTH_MODE", "dev")
        monkeypatch.setenv("SECRET_KEY", "test-secret")

        with patch("dotenv.load_dotenv", return_value=True):
            module = _load_settings_module("test_settings_swagger_sidecar")

        assert "drf_spectacular_sidecar" in module.INSTALLED_APPS
        assert module.SPECTACULAR_SETTINGS["SWAGGER_UI_DIST"] == "SIDECAR"
        assert module.SPECTACULAR_SETTINGS["SWAGGER_UI_FAVICON_HREF"] == "SIDECAR"
        assert module.SPECTACULAR_SETTINGS["REDOC_DIST"] == "SIDECAR"


class TestSettingsLdapConfig:
    """Tests for LDAP configuration exported by settings."""

    def test_missing_ldap_settings_in_iis_mode_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """IIS mode requires LDAP_SERVER_URI and LDAP_BASE_DN at import time."""
        monkeypatch.setenv("AUTH_MODE", "iis")
        monkeypatch.setenv("SECRET_KEY", "test-secret")
        monkeypatch.setenv("LDAP_SERVER_URI", "")
        monkeypatch.setenv("LDAP_BASE_DN", "")

        with patch("dotenv.load_dotenv", return_value=True):
            with pytest.raises(
                ImproperlyConfigured,
                match="LDAP_SERVER_URI and LDAP_BASE_DN are required",
            ):
                _load_settings_module("test_settings_missing_ldap_iis")

    def test_ldap_settings_are_exported_when_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """LDAP settings are available for the future real group lookup implementation."""
        monkeypatch.setenv("AUTH_MODE", "iis")
        monkeypatch.setenv("SECRET_KEY", "test-secret")
        monkeypatch.setenv("LDAP_SERVER_URI", "ldap://dc.corp.local")
        monkeypatch.setenv("LDAP_BASE_DN", "DC=corp,DC=local")

        with patch("dotenv.load_dotenv", return_value=True):
            module = _load_settings_module("test_settings_ldap_configured")

        assert module.LDAP_SERVER_URI == "ldap://dc.corp.local"
        assert module.LDAP_BASE_DN == "DC=corp,DC=local"
