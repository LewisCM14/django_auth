"""Tests for Oracle-backed equipment serial endpoint."""

from __future__ import annotations

from copy import deepcopy

import pytest
from django.core.cache import cache
from django.test import Client

from api.views.invoice import InvoiceListView


class _StubOracleAdapter:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows
        self.calls: list[tuple[str, object]] = []

    def fetch_all(self, sql: str, params: object = None) -> list[dict[str, object]]:
        self.calls.append((sql, params))
        return deepcopy(self._rows)


class TestInvoiceListView:
    @pytest.mark.django_db
    def test_admin_returns_serial_number_list(
        self, admin_client: Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cache.clear()
        adapter = _StubOracleAdapter(
            [{"serial_number": "SN-100"}, {"serial_number": "SN-101"}]
        )
        monkeypatch.setattr(
            InvoiceListView, "oracle_adapter_provider", staticmethod(lambda: adapter)
        )
        response = admin_client.get("/api/equipment/pump/serial_numbers/")
        assert response.status_code == 200
        assert response.json() == {"count": 2, "results": ["SN-100", "SN-101"]}

    @pytest.mark.django_db
    def test_uses_path_equipment_name_as_query_value(
        self, admin_client: Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cache.clear()
        adapter = _StubOracleAdapter([{"serial_number": "SN-100"}])
        monkeypatch.setattr(
            InvoiceListView, "oracle_adapter_provider", staticmethod(lambda: adapter)
        )

        response = admin_client.get("/api/equipment/pump_101/serial_numbers/")

        assert response.status_code == 200
        assert adapter.calls[0][1] == {"name": "pump_101"}

    @pytest.mark.django_db
    def test_legacy_invoice_route_supports_name_query_param(
        self, admin_client: Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cache.clear()
        adapter = _StubOracleAdapter([{"serial_number": "SN-200"}])
        monkeypatch.setattr(
            InvoiceListView, "oracle_adapter_provider", staticmethod(lambda: adapter)
        )

        response = admin_client.get("/api/invoices/?name=pump")

        assert response.status_code == 200
        assert response.json() == {"count": 1, "results": ["SN-200"]}
        assert adapter.calls[0][1] == {"name": "pump"}
