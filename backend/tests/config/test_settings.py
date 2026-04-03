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


def test_invalid_auth_mode_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Importing settings fails fast when AUTH_MODE is invalid."""
    monkeypatch.setenv("AUTH_MODE", "invalid")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("ALLOWED_HOSTS", "localhost")

    with patch("dotenv.load_dotenv", return_value=True):
        with pytest.raises(ImproperlyConfigured, match="AUTH_MODE must be either"):
            _load_settings_module("test_settings_invalid_auth_mode")


def test_missing_secret_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Importing settings fails when SECRET_KEY is empty."""
    monkeypatch.setenv("AUTH_MODE", "dev")
    monkeypatch.setenv("SECRET_KEY", "")
    monkeypatch.setenv("ALLOWED_HOSTS", "localhost")

    with patch("dotenv.load_dotenv", return_value=True):
        with pytest.raises(ImproperlyConfigured, match="SECRET_KEY is required"):
            _load_settings_module("test_settings_missing_secret")


def test_allowed_hosts_defaults_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """ALLOWED_HOSTS falls back to localhost defaults when not configured."""
    monkeypatch.setenv("AUTH_MODE", "dev")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("ALLOWED_HOSTS", "")

    with patch("dotenv.load_dotenv", return_value=True):
        module = _load_settings_module("test_settings_allowed_hosts_default")

    assert module.ALLOWED_HOSTS == ["localhost", "127.0.0.1"]


def test_logging_config_has_request_id_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    """LOGGING dict exposes the request_id filter for handler attachment."""
    monkeypatch.setenv("AUTH_MODE", "dev")
    monkeypatch.setenv("SECRET_KEY", "test-secret")

    with patch("dotenv.load_dotenv", return_value=True):
        module = _load_settings_module("test_settings_logging_filter")

    assert "request_id" in module.LOGGING["filters"]


def test_logging_config_console_handler_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    """LOGGING dict includes a console handler wired to stderr."""
    monkeypatch.setenv("AUTH_MODE", "dev")
    monkeypatch.setenv("SECRET_KEY", "test-secret")

    with patch("dotenv.load_dotenv", return_value=True):
        module = _load_settings_module("test_settings_logging_console")

    handler = module.LOGGING["handlers"]["console"]
    assert handler["class"] == "logging.StreamHandler"
    assert handler["stream"] == "ext://sys.stderr"
    assert "request_id" in handler["filters"]


def test_default_cache_backend_is_locmem(monkeypatch: pytest.MonkeyPatch) -> None:
    """CACHES defaults to LocMemCache when CACHE_BACKEND is unset."""
    monkeypatch.setenv("AUTH_MODE", "dev")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.delenv("CACHE_BACKEND", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)

    with patch("dotenv.load_dotenv", return_value=True):
        module = _load_settings_module("test_settings_default_cache_locmem")

    assert "LocMemCache" in module.CACHES["default"]["BACKEND"]


def test_redis_cache_backend_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """CACHES uses django-redis backend when CACHE_BACKEND=redis."""
    monkeypatch.setenv("AUTH_MODE", "dev")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("CACHE_BACKEND", "redis")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    with patch("dotenv.load_dotenv", return_value=True):
        module = _load_settings_module("test_settings_redis_cache")

    cache_config = module.CACHES["default"]
    assert cache_config["BACKEND"] == "django_redis.cache.RedisCache"
    assert cache_config["LOCATION"] == "redis://localhost:6379/0"


def test_redis_backend_without_url_raises_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Importing settings fails when redis backend is selected without REDIS_URL."""
    monkeypatch.setenv("AUTH_MODE", "dev")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("CACHE_BACKEND", "redis")
    monkeypatch.delenv("REDIS_URL", raising=False)

    with patch("dotenv.load_dotenv", return_value=True):
        with pytest.raises(
            ImproperlyConfigured,
            match="REDIS_URL is required when CACHE_BACKEND=redis",
        ):
            _load_settings_module("test_settings_redis_missing_url")
