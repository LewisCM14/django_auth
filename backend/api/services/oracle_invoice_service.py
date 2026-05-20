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
SELECT DISTINCT serial_number
FROM equipment_table
WHERE equipment_name = :name
AND serial_number IS NOT NULL
""".strip()

_ORACLE_SERVICE_ACTION = "list equipment serial numbers from oracle"
_ORACLE_SERVICE_RESOURCE = "oracle:equipment-serials"


def _seconds_until_next_friday_11(now: datetime | None = None) -> int:
    current = now or datetime.now()
    friday_index = 4
    days_ahead = (friday_index - current.weekday()) % 7
    next_reset = current.replace(hour=11, minute=0, second=0, microsecond=0) + timedelta(
        days=days_ahead
    )
    if next_reset <= current:
        next_reset += timedelta(days=7)
    return max(1, int((next_reset - current).total_seconds()))


def _coerce_serial(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip()
    return str(value).strip()


@lru_cache(maxsize=1)
def get_oracle_adapter() -> OracleAdapter:
    return create_oracle_adapter_from_env()


def list_equipment_serial_numbers(
    *,
    name: str,
    request: Any | None = None,
    adapter: OracleAdapter | None = None,
) -> list[str]:
    started = time.perf_counter()
    oracle_adapter = adapter if adapter is not None else get_oracle_adapter()

    cache_key = service_key("equipment", "serial_numbers", {"name": name})
    cached = cache.get(cache_key)
    if isinstance(cached, list):
        return [str(item) for item in cached]

    raw_rows = oracle_adapter.fetch_all(_EQUIPMENT_SERIAL_SQL, {"name": name})
    serial_numbers = [_coerce_serial(row["serial_number"]) for row in raw_rows]

    cache.set(cache_key, serial_numbers, timeout=_seconds_until_next_friday_11())

    logger.info(
        "oracle equipment serial service query completed",
        extra=build_security_event_fields(
            request,
            event_type="ORACLE_SERVICE_QUERY_SUCCESS",
            action_attempted=_ORACLE_SERVICE_ACTION,
            result="success",
            resource_accessed=_ORACLE_SERVICE_RESOURCE,
            duration_ms=(time.perf_counter() - started) * 1000,
            oracle_row_count=len(serial_numbers),
            equipment_name=name,
        ),
    )
    return serial_numbers
