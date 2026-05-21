"""Tests for Oracle-backed equipment serial endpoint."""

from __future__ import annotations

from copy import deepcopy

import pytest
from django.core.cache import cache
from django.test import Client

from api.views.equipment import EquipmentListView


class _StubOracleAdapter:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows
        self.calls: list[tuple[str, object]] = []

    def fetch_all(self, sql: str, params: object = None) -> list[dict[str, object]]:
        self.calls.append((sql, params))
        return deepcopy(self._rows)


class TestEquipmentListView:
    @pytest.mark.django_db
    def test_admin_returns_equipment_hierarchy(
        self, admin_client: Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cache.clear()
        adapter = _StubOracleAdapter(
            [
                {
                    "equipment_name": "pump",
                    "equipment_id": "EQ-1",
                    "system": "Cooling",
                    "sub_system": "Motor",
                    "serial_number": "SN-100",
                    "type": "Core",
                    "description": "Primary",
                },
                {
                    "equipment_name": "pump",
                    "equipment_id": "EQ-1",
                    "system": "Cooling",
                    "sub_system": "Motor",
                    "serial_number": "SN-101",
                    "type": "Core",
                    "description": "Secondary",
                },
            ]
        )
        monkeypatch.setattr(
            EquipmentListView, "oracle_adapter_provider", staticmethod(lambda: adapter)
        )
        response = admin_client.get("/api/equipment/pump/serial_numbers/")
        assert response.status_code == 200
        assert response.json() == {
            "equipment_id": "EQ-1",
            "equipment": "pump",
            "system": "Cooling",
            "subsystems": [
                {
                    "subsystem": "Motor",
                    "serials": [
                        {
                            "serial_number": "SN-100",
                            "type": "Core",
                            "description": "Primary",
                        },
                        {
                            "serial_number": "SN-101",
                            "type": "Core",
                            "description": "Secondary",
                        },
                    ],
                }
            ],
        }

    @pytest.mark.django_db
    def test_uses_path_equipment_name_as_query_value(
        self, admin_client: Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cache.clear()
        adapter = _StubOracleAdapter([])
        monkeypatch.setattr(
            EquipmentListView, "oracle_adapter_provider", staticmethod(lambda: adapter)
        )

        response = admin_client.get("/api/equipment/pump_101/serial_numbers/")

        assert response.status_code == 200
        assert adapter.calls[0][1] == {"name": "pump_101"}

    @pytest.mark.django_db
    def test_blank_equipment_name_returns_validation_error(
        self, admin_client: Client
    ) -> None:
        response = admin_client.get("/api/equipment/%20%20/serial_numbers/")

        assert response.status_code == 400
        body = response.json()
        assert body["equipment_name"] == ["This path parameter may not be blank."]
        assert isinstance(body["request_id"], str) and body["request_id"]
