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

    def test_invalid_cors_allowed_origin_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Importing settings fails when a CORS origin is malformed."""
        monkeypatch.setenv("AUTH_MODE", "dev")
        monkeypatch.setenv("SECRET_KEY", "test-secret")
        monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://frontend.example.com/path")

        with patch("dotenv.load_dotenv", return_value=True):
            with pytest.raises(ImproperlyConfigured, match="CORS_ALLOWED_ORIGINS"):
                _load_settings_module("test_settings_invalid_cors_origin")

    def test_missing_allowed_hosts_in_iis_mode_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Importing settings fails when IIS mode has no explicit ALLOWED_HOSTS."""
        monkeypatch.setenv("AUTH_MODE", "iis")
        monkeypatch.setenv("SECRET_KEY", "test-secret")
        monkeypatch.setenv("LDAP_SERVER_URI", "ldap://dc.corp.local")
        monkeypatch.setenv("LDAP_BASE_DN", "DC=corp,DC=local")
        monkeypatch.setenv("ALLOWED_HOSTS", "")

        with patch("dotenv.load_dotenv", return_value=True):
            with pytest.raises(ImproperlyConfigured, match="ALLOWED_HOSTS"):
                _load_settings_module("test_settings_missing_allowed_hosts_iis")


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

    def test_django_server_logger_is_silenced(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Runserver's built-in request logger is disabled to avoid duplicate access logs."""
        monkeypatch.setenv("AUTH_MODE", "dev")
        monkeypatch.setenv("SECRET_KEY", "test-secret")

        with patch("dotenv.load_dotenv", return_value=True):
            module = _load_settings_module("test_settings_django_server_logger")

        assert module.LOGGING["loggers"]["django.server"]["handlers"] == []
        assert module.LOGGING["loggers"]["django.server"]["propagate"] is False


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


class TestSettingsSecurityConfig:
    """Tests for security-oriented Django settings."""

    def test_security_headers_defaults_in_dev_mode(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Development mode keeps transport headers conservative and local-only."""
        monkeypatch.setenv("AUTH_MODE", "dev")
        monkeypatch.setenv("SECRET_KEY", "test-secret")

        with patch("dotenv.load_dotenv", return_value=True):
            module = _load_settings_module("test_settings_security_dev")

        assert module.SECURE_PROXY_SSL_HEADER is None
        assert module.SECURE_HSTS_SECONDS == 0
        assert module.SESSION_COOKIE_SECURE is False
        assert module.CSRF_COOKIE_SECURE is False
        assert module.CORS_ALLOW_ALL_ORIGINS is False
        assert module.CORS_ALLOW_CREDENTIALS is True
        assert module.CORS_ALLOWED_ORIGINS == []
        assert "script-src 'self'" in module.CONTENT_SECURITY_POLICY
        assert "style-src 'self'" in module.CONTENT_SECURITY_POLICY

    def test_security_headers_are_enabled_for_iis_mode(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """IIS mode enables hardened transport and cookie settings."""
        monkeypatch.setenv("AUTH_MODE", "iis")
        monkeypatch.setenv("SECRET_KEY", "test-secret")
        monkeypatch.setenv("ALLOWED_HOSTS", "app.corp.local")
        monkeypatch.setenv("LDAP_SERVER_URI", "ldap://dc.corp.local")
        monkeypatch.setenv("LDAP_BASE_DN", "DC=corp,DC=local")
        monkeypatch.setenv(
            "CORS_ALLOWED_ORIGINS",
            "https://portal.corp.local,https://intranet.corp.local",
        )

        with patch("dotenv.load_dotenv", return_value=True):
            module = _load_settings_module("test_settings_security_iis")

        assert module.SECURE_PROXY_SSL_HEADER == ("HTTP_X_FORWARDED_PROTO", "https")
        assert module.SECURE_SSL_REDIRECT is False
        assert module.SECURE_HSTS_SECONDS == 31536000
        assert module.SECURE_HSTS_INCLUDE_SUBDOMAINS is True
        assert module.SECURE_HSTS_PRELOAD is False
        assert module.SECURE_CONTENT_TYPE_NOSNIFF is True
        assert module.SECURE_REFERRER_POLICY == "same-origin"
        assert module.X_FRAME_OPTIONS == "DENY"
        assert module.SESSION_COOKIE_SECURE is True
        assert module.SESSION_COOKIE_HTTPONLY is True
        assert module.SESSION_COOKIE_SAMESITE == "Lax"
        assert module.CSRF_COOKIE_SECURE is True
        assert module.CSRF_COOKIE_HTTPONLY is True
        assert module.CSRF_COOKIE_SAMESITE == "Lax"
        assert module.CORS_ALLOW_ALL_ORIGINS is False
        assert module.CORS_ALLOW_CREDENTIALS is True
        assert module.CORS_ALLOWED_ORIGINS == [
            "https://portal.corp.local",
            "https://intranet.corp.local",
        ]
        assert "script-src 'self'" in module.CONTENT_SECURITY_POLICY
        assert "style-src 'self'" in module.CONTENT_SECURITY_POLICY

    def test_secure_ssl_redirect_can_be_enabled_explicitly(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """SECURE_SSL_REDIRECT follows explicit environment opt-in."""
        monkeypatch.setenv("AUTH_MODE", "iis")
        monkeypatch.setenv("SECRET_KEY", "test-secret")
        monkeypatch.setenv("ALLOWED_HOSTS", "app.corp.local")
        monkeypatch.setenv("LDAP_SERVER_URI", "ldap://dc.corp.local")
        monkeypatch.setenv("LDAP_BASE_DN", "DC=corp,DC=local")
        monkeypatch.setenv("SECURE_SSL_REDIRECT", "true")

        with patch("dotenv.load_dotenv", return_value=True):
            module = _load_settings_module("test_settings_security_iis_ssl_redirect")

        assert module.SECURE_SSL_REDIRECT is True


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

    def test_swagger_ui_uses_sidecar_assets(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
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

    def test_invalid_ldap_server_uri_in_iis_mode_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """IIS mode rejects malformed LDAP server URIs."""
        monkeypatch.setenv("AUTH_MODE", "iis")
        monkeypatch.setenv("SECRET_KEY", "test-secret")
        monkeypatch.setenv("ALLOWED_HOSTS", "app.corp.local")
        monkeypatch.setenv("LDAP_SERVER_URI", "http://dc.corp.local")
        monkeypatch.setenv("LDAP_BASE_DN", "DC=corp,DC=local")

        with patch("dotenv.load_dotenv", return_value=True):
            with pytest.raises(ImproperlyConfigured, match="LDAP_SERVER_URI"):
                _load_settings_module("test_settings_invalid_ldap_uri")

    def test_invalid_ldap_base_dn_in_iis_mode_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """IIS mode rejects malformed LDAP base DNs."""
        monkeypatch.setenv("AUTH_MODE", "iis")
        monkeypatch.setenv("SECRET_KEY", "test-secret")
        monkeypatch.setenv("ALLOWED_HOSTS", "app.corp.local")
        monkeypatch.setenv("LDAP_SERVER_URI", "ldap://dc.corp.local")
        monkeypatch.setenv("LDAP_BASE_DN", "not-a-dn")

        with patch("dotenv.load_dotenv", return_value=True):
            with pytest.raises(ImproperlyConfigured, match="LDAP_BASE_DN"):
                _load_settings_module("test_settings_invalid_ldap_dn")
