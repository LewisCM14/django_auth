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
    def test_admin_returns_serial_number_list(self, admin_client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
        cache.clear()
        adapter = _StubOracleAdapter([{"serial_number": "SN-100"}, {"serial_number": "SN-101"}])
        monkeypatch.setattr(InvoiceListView, "oracle_adapter_provider", staticmethod(lambda: adapter))
        response = admin_client.get("/api/invoices/?name=pump")
        assert response.status_code == 200
        assert response.json() == {"count": 2, "results": ["SN-100", "SN-101"]}

    @pytest.mark.django_db
    def test_missing_name_returns_400_and_skips_adapter(self, admin_client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
        adapter = _StubOracleAdapter([])
        monkeypatch.setattr(InvoiceListView, "oracle_adapter_provider", staticmethod(lambda: adapter))
        response = admin_client.get("/api/invoices/")
        assert response.status_code == 400
        assert "name" in response.json()
        assert adapter.calls == []
