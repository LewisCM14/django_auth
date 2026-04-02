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
