"""Service-layer orchestration for Oracle-backed equipment serial reads."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any

from django.core.cache import cache

from api.adapters.oracle import OracleAdapter, create_oracle_adapter_from_env
from api.cache_keys import service_key
from api.security_logging import build_security_event_fields

logger = logging.getLogger(__name__)

_EQUIPMENT_SERIAL_SQL = """
SELECT
  e.equipment_name,
  e.equipment_id,
  e.system,
  c.sub_system,
  e.serial_number,
  c.type,
  c.description
FROM equipment_table e
INNER JOIN component_table c ON e.serial_number = c.serial_number
WHERE e.equipment_name = :name
AND e.serial_number IS NOT NULL
""".strip()

_ORACLE_SERVICE_ACTION = "list equipment serial hierarchy from oracle"
_ORACLE_SERVICE_RESOURCE = "oracle:equipment-serial-hierarchy"


def _seconds_until_next_friday_11(now: datetime | None = None) -> int:
    current = now or datetime.now()
    friday_index = 4
    days_ahead = (friday_index - current.weekday()) % 7
    next_reset = current.replace(
        hour=11, minute=0, second=0, microsecond=0
    ) + timedelta(days=days_ahead)
    if next_reset <= current:
        next_reset += timedelta(days=7)
    return max(1, int((next_reset - current).total_seconds()))


def _to_text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip()
    return str(value).strip()


@lru_cache(maxsize=1)
def get_oracle_adapter() -> OracleAdapter:
    return create_oracle_adapter_from_env()


def get_equipment_serial_hierarchy(
    *,
    name: str,
    request: Any | None = None,
    adapter: OracleAdapter | None = None,
) -> dict[str, object]:
    started = time.perf_counter()
    oracle_adapter = adapter if adapter is not None else get_oracle_adapter()

    cache_key = service_key("equipment", "serial_hierarchy", {"name": name})
    cached = cache.get(cache_key)
    if isinstance(cached, dict):
        return cached

    raw_rows = oracle_adapter.fetch_all(_EQUIPMENT_SERIAL_SQL, {"name": name})
    if not raw_rows:
        empty_result: dict[str, object] = {
            "equipment_id": "",
            "equipment": name,
            "system": "",
            "sub-systems": [],
        }
        cache.set(cache_key, empty_result, timeout=_seconds_until_next_friday_11())
        return empty_result

    first = raw_rows[0]
    result: dict[str, object] = {
        "equipment_id": _to_text(first["equipment_id"]),
        "equipment": _to_text(first["equipment_name"]),
        "system": _to_text(first["system"]),
        "sub-systems": [],
    }

    buckets: dict[str, list[dict[str, str]]] = {}
    for row in raw_rows:
        subsystem = _to_text(row["sub_system"])
        buckets.setdefault(subsystem, []).append(
            {
                "serial_number": _to_text(row["serial_number"]),
                "type": _to_text(row["type"]),
                "description": _to_text(row["description"]),
            }
        )

    result["sub-systems"] = [
        {"sub-system": subsystem, "serials": serials}
        for subsystem, serials in buckets.items()
    ]

    cache.set(cache_key, result, timeout=_seconds_until_next_friday_11())

    logger.info(
        "oracle equipment serial hierarchy service query completed",
        extra=build_security_event_fields(
            request,
            event_type="ORACLE_SERVICE_QUERY_SUCCESS",
            action_attempted=_ORACLE_SERVICE_ACTION,
            result="success",
            resource_accessed=_ORACLE_SERVICE_RESOURCE,
            duration_ms=(time.perf_counter() - started) * 1000,
            oracle_row_count=len(raw_rows),
            equipment_name=name,
        ),
    )
    return result
