"""Service-layer orchestration for Oracle-backed invoice reads.

This module keeps view code transport-focused by centralizing:
- Oracle adapter lifecycle and memoization.
- Invoice list query execution.
- Structured service-level success logging.

Authorization and input validation are intentionally handled in the view layer.
"""

from __future__ import annotations

import logging
import time
from functools import lru_cache
from typing import Any, TypedDict

from api.adapters.oracle import OracleAdapter, OracleRow, create_oracle_adapter_from_env
from api.security_logging import build_security_event_fields

logger = logging.getLogger(__name__)


class InvoiceBffRow(TypedDict):
    """Normalized invoice row returned to BFF clients."""

    invoice_id: str
    status: str
    status_label: str
    is_closed: bool


_INVOICE_LIST_SQL = """
SELECT invoice_id, status
FROM (
    SELECT invoice_id, status
    FROM invoices
    WHERE (:status IS NULL OR status = :status)
    ORDER BY invoice_id
)
WHERE ROWNUM <= :max_rows
""".strip()

_ORACLE_SERVICE_ACTION = "list invoices from oracle"
_ORACLE_SERVICE_RESOURCE = "oracle:invoices"
_CLOSED_STATUSES = frozenset({"PAID", "VOID", "CANCELLED", "CLOSED"})


def _coerce_text(value: object, *, default: str = "") -> str:
    """Convert common Oracle-native values to normalized text."""

    if value is None:
        return default
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip()
    return str(value).strip()


def _normalize_status(value: object) -> str:
    """Return an uppercase status token with UNKNOWN fallback."""

    normalized = _coerce_text(value, default="UNKNOWN").upper()
    return normalized if normalized else "UNKNOWN"


def _normalize_invoice_row(row: OracleRow) -> InvoiceBffRow:
    """Map raw Oracle adapter row values to the stable BFF response shape."""

    invoice_id = _coerce_text(row.get("invoice_id"), default="UNKNOWN")
    if not invoice_id:
        invoice_id = "UNKNOWN"

    status = _normalize_status(row.get("status"))
    return {
        "invoice_id": invoice_id.upper(),
        "status": status,
        "status_label": status.replace("_", " ").title(),
        "is_closed": status in _CLOSED_STATUSES,
    }


@lru_cache(maxsize=1)
def get_oracle_adapter() -> OracleAdapter:
    """Return the memoized Oracle adapter used by invoice service calls.

    The ``lru_cache(maxsize=1)`` decorator keeps one adapter instance per
    process, which allows connection-pool reuse and avoids repeated adapter
    construction cost.
    """

    return create_oracle_adapter_from_env()


def list_invoices(
    *,
    status: str | None,
    limit: int,
    request: Any | None = None,
    adapter: OracleAdapter | None = None,
) -> list[InvoiceBffRow]:
    """Fetch invoice rows from Oracle using validated query inputs.

    Args:
        status: Optional status filter. ``None`` returns rows across all
            statuses. Callers should provide already validated values.
        limit: Maximum number of rows returned by the query.
        request: Optional request object used only for log correlation fields.
        adapter: Optional adapter override for tests/custom call sites. When
            omitted, the shared adapter from ``get_oracle_adapter`` is used.

    Returns:
        Normalized invoice rows in the BFF response shape.

    Raises:
        Exception: Propagates adapter/database errors unchanged so global
            exception handling can produce standardized API responses.
    """

    started = time.perf_counter()
    oracle_adapter = adapter if adapter is not None else get_oracle_adapter()
    # Query retries, adapter cache behavior, and low-level query logging are
    # handled within OracleAdapter.
    raw_rows = oracle_adapter.fetch_all(
        _INVOICE_LIST_SQL,
        {
            "status": status,
            "max_rows": limit,
        },
    )
    rows = [_normalize_invoice_row(row) for row in raw_rows]

    # Emit service-level success telemetry for endpoint/business observability.
    logger.info(
        "oracle invoice service query completed",
        extra=build_security_event_fields(
            request,
            event_type="ORACLE_SERVICE_QUERY_SUCCESS",
            action_attempted=_ORACLE_SERVICE_ACTION,
            result="success",
            resource_accessed=_ORACLE_SERVICE_RESOURCE,
            duration_ms=(time.perf_counter() - started) * 1000,
            oracle_row_count=len(rows),
            oracle_status_filter=status,
            oracle_limit=limit,
        ),
    )
    return rows
