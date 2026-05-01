"""Tests for Oracle invoice service helpers."""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any, cast

import pytest

from api.services.oracle_invoice_service import get_oracle_adapter, list_invoices


class _StubOracleAdapter:
    """Adapter stub for service-level unit tests."""

    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows
        self.calls: list[tuple[str, object]] = []

    def fetch_all(self, sql: str, params: object = None) -> list[dict[str, object]]:
        self.calls.append((sql, params))
        return deepcopy(self._rows)


class TestOracleInvoiceService:
    """Tests for invoice query orchestration and adapter provider caching."""

    def test_list_invoices_executes_expected_sql_and_params(self) -> None:
        """Service sends normalized filter params to the Oracle adapter."""

        adapter = _StubOracleAdapter([{"invoice_id": "A100", "status": "PAID"}])

        rows = list_invoices(status="PAID", limit=25, adapter=cast(Any, adapter))

        assert rows == [
            {
                "invoice_id": "A100",
                "status": "PAID",
                "status_label": "Paid",
                "is_closed": True,
            }
        ]
        assert len(adapter.calls) == 1
        assert "FROM invoices" in adapter.calls[0][0]
        assert adapter.calls[0][1] == {"status": "PAID", "max_rows": 25}

    def test_list_invoices_normalizes_native_oracle_values(self) -> None:
        """Service normalizes raw native values into stable BFF fields."""

        adapter = _StubOracleAdapter(
            [
                {"invoice_id": 1001, "status": b"paid"},
                {"invoice_id": " inv-22 ", "status": None},
            ]
        )

        rows = list_invoices(status=None, limit=10, adapter=cast(Any, adapter))

        assert rows == [
            {
                "invoice_id": "1001",
                "status": "PAID",
                "status_label": "Paid",
                "is_closed": True,
            },
            {
                "invoice_id": "INV-22",
                "status": "UNKNOWN",
                "status_label": "Unknown",
                "is_closed": False,
            },
        ]

    def test_list_invoices_falls_back_when_invoice_id_is_blank(self) -> None:
        """Service maps blank invoice identifiers to UNKNOWN for BFF stability."""

        adapter = _StubOracleAdapter(
            [
                {"invoice_id": "   ", "status": "open"},
            ]
        )

        rows = list_invoices(status=None, limit=5, adapter=cast(Any, adapter))

        assert rows == [
            {
                "invoice_id": "UNKNOWN",
                "status": "OPEN",
                "status_label": "Open",
                "is_closed": False,
            }
        ]

    def test_list_invoices_emits_structured_success_log(
        self,
        caplog: pytest.LogCaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Service emits structured success fields for observability."""

        monkeypatch.setattr(logging.getLogger("api"), "propagate", True)
        adapter = _StubOracleAdapter([{"invoice_id": "A100", "status": "PAID"}])

        with caplog.at_level(
            logging.INFO, logger="api.services.oracle_invoice_service"
        ):
            _ = list_invoices(status=None, limit=10, adapter=cast(Any, adapter))

        record = cast(
            Any,
            next(
                rec
                for rec in caplog.records
                if rec.name == "api.services.oracle_invoice_service"
            ),
        )
        assert record.event_type == "ORACLE_SERVICE_QUERY_SUCCESS"
        assert record.action_attempted == "list invoices from oracle"
        assert record.resource_accessed == "oracle:invoices"
        assert record.oracle_row_count == 1
        assert record.oracle_limit == 10

    def test_get_oracle_adapter_is_cached(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Adapter provider memoizes singleton instance for pool reuse."""

        created: list[object] = []
        sentinel_adapter = object()

        def _factory() -> object:
            created.append(object())
            return sentinel_adapter

        get_oracle_adapter.cache_clear()
        monkeypatch.setattr(
            "api.services.oracle_invoice_service.create_oracle_adapter_from_env",
            _factory,
        )

        first = get_oracle_adapter()
        second = get_oracle_adapter()

        assert first is sentinel_adapter
        assert second is sentinel_adapter
        assert len(created) == 1
        get_oracle_adapter.cache_clear()
