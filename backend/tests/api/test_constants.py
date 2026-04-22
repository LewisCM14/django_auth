"""Tests for env-driven constants and AD group mapping."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from django.core.exceptions import ImproperlyConfigured


CONSTANTS_PATH = Path(__file__).resolve().parents[2] / "api" / "constants.py"


def _load_constants_module(module_name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, CONSTANTS_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to build import spec for api.constants")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestAdGroupMapping:
    """Tests for the AD group to role mapping loaded from the environment."""

    def test_ad_group_mapping_is_loaded_from_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The mapping uses deployment env values instead of hardcoded DNs."""
        admin_group = "CN=qa-admins,OU=Groups,DC=corp,DC=local"
        viewer_group = "CN=qa-viewers,OU=Groups,DC=corp,DC=local"

        monkeypatch.setenv("ADMIN_AD_GROUP", admin_group)
        monkeypatch.setenv("VIEWER_AD_GROUP", viewer_group)

        module = _load_constants_module("test_constants_env_mapping")

        assert module.ADMIN_AD_GROUP == admin_group
        assert module.VIEWER_AD_GROUP == viewer_group
        assert module.AD_GROUP_TO_ROLE_MAP == {
            admin_group: "app_admin",
            viewer_group: "app_viewer",
        }

    @pytest.mark.parametrize(
        ("missing_env_name", "present_env_name", "present_value"),
        [
            (
                "ADMIN_AD_GROUP",
                "VIEWER_AD_GROUP",
                "CN=qa-viewers,OU=Groups,DC=corp,DC=local",
            ),
            (
                "VIEWER_AD_GROUP",
                "ADMIN_AD_GROUP",
                "CN=qa-admins,OU=Groups,DC=corp,DC=local",
            ),
        ],
    )
    def test_missing_ad_group_env_var_raises(
        self,
        monkeypatch: pytest.MonkeyPatch,
        missing_env_name: str,
        present_env_name: str,
        present_value: str,
    ) -> None:
        """Importing constants fails fast when an AD group env var is missing."""
        monkeypatch.delenv("ADMIN_AD_GROUP", raising=False)
        monkeypatch.delenv("VIEWER_AD_GROUP", raising=False)
        monkeypatch.setenv(present_env_name, present_value)

        with pytest.raises(ImproperlyConfigured, match=missing_env_name):
            _load_constants_module(f"test_constants_missing_{missing_env_name}")

    def test_duplicate_ad_group_values_raise(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Importing constants fails if both roles point at the same AD group."""
        shared_group = "CN=qa-shared,OU=Groups,DC=corp,DC=local"

        monkeypatch.setenv("ADMIN_AD_GROUP", shared_group)
        monkeypatch.setenv("VIEWER_AD_GROUP", shared_group)

        with pytest.raises(
            ImproperlyConfigured,
            match="must reference different AD groups",
        ):
            _load_constants_module("test_constants_duplicate_groups")
