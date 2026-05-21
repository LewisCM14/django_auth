"""Tests for Oracle equipment serial service helpers."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any, cast

from django.core.cache import cache

from api.services.oracle_equipment_service import (
    _seconds_until_next_friday_11,
    get_equipment_serial_hierarchy,
    get_oracle_adapter,
)


class _StubOracleAdapter:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows
        self.calls: list[tuple[str, object]] = []

    def fetch_all(self, sql: str, params: object = None) -> list[dict[str, object]]:
        self.calls.append((sql, params))
        return deepcopy(self._rows)


class TestOracleEquipmentSerialService:
    def test_query_executes_expected_sql_and_params(self) -> None:
        cache.clear()
        adapter = _StubOracleAdapter([])
        _ = get_equipment_serial_hierarchy(name="Pump", adapter=cast(Any, adapter))
        assert "FROM equipment_table" in adapter.calls[0][0]
        assert "INNER JOIN component_table" in adapter.calls[0][0]
        assert adapter.calls[0][1] == {"name": "Pump"}

    def test_hierarchy_groups_rows_by_subsystem(self) -> None:
        cache.clear()
        adapter = _StubOracleAdapter(
            [
                {
                    "equipment_name": b" Pump ",
                    "equipment_id": 1001,
                    "system": "Cooling",
                    "sub_system": "A",
                    "serial_number": "SN-1",
                    "type": "T1",
                    "description": "D1",
                },
                {
                    "equipment_name": "Pump",
                    "equipment_id": "1001",
                    "system": "Cooling",
                    "sub_system": "A",
                    "serial_number": b" SN-2 ",
                    "type": "T2",
                    "description": "D2",
                },
            ]
        )
        rows = get_equipment_serial_hierarchy(name="Pump", adapter=cast(Any, adapter))
        assert rows == {
            "equipment_id": "1001",
            "equipment": "Pump",
            "system": "Cooling",
            "sub-systems": [
                {
                    "sub-system": "A",
                    "serials": [
                        {"serial_number": "SN-1", "type": "T1", "description": "D1"},
                        {"serial_number": "SN-2", "type": "T2", "description": "D2"},
                    ],
                }
            ],
        }

    def test_service_cache_prevents_repeat_call(self) -> None:
        cache.clear()
        adapter = _StubOracleAdapter([])
        _ = get_equipment_serial_hierarchy(name="Pump", adapter=cast(Any, adapter))
        _ = get_equipment_serial_hierarchy(name="Pump", adapter=cast(Any, adapter))
        assert len(adapter.calls) == 1

    def test_friday_cache_break_calculation(self) -> None:
        now = datetime(2026, 5, 15, 10, 0, 0)
        assert _seconds_until_next_friday_11(now) == 3600

    def test_friday_cache_break_rolls_to_next_week_after_cutoff(self) -> None:
        now = datetime(2026, 5, 15, 12, 0, 0)
        assert _seconds_until_next_friday_11(now) == 601200

    def test_get_oracle_adapter_is_cached(self, monkeypatch: Any) -> None:
        created: list[object] = []
        sentinel_adapter = object()

        def _factory() -> object:
            created.append(object())
            return sentinel_adapter

        get_oracle_adapter.cache_clear()
        monkeypatch.setattr(
            "api.services.oracle_equipment_service.create_oracle_adapter_from_env",
            _factory,
        )
        first = get_oracle_adapter()
        second = get_oracle_adapter()
        assert first is sentinel_adapter
        assert second is sentinel_adapter
        assert len(created) == 1
        get_oracle_adapter.cache_clear()
