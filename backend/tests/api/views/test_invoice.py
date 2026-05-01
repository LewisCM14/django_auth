"""Tests for Oracle-backed invoice endpoint."""

from __future__ import annotations

from copy import deepcopy

import pytest
from django.core.cache import cache
from django.test import Client

from api.views.invoice import InvoiceListView


class _StubOracleAdapter:
    """In-memory adapter stub for invoice endpoint tests."""

    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows
        self.calls: list[tuple[str, object]] = []

    def fetch_all(self, sql: str, params: object = None) -> list[dict[str, object]]:
        self.calls.append((sql, params))
        return deepcopy(self._rows)


class TestInvoiceListView:
    """Tests for `GET /api/invoices/` behavior and guardrails."""

    @pytest.mark.django_db
    def test_admin_returns_invoice_list(
        self,
        admin_client: Client,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Admin users can read invoice rows from the endpoint."""

        adapter = _StubOracleAdapter(
            [
                {"invoice_id": "A100", "status": "PAID"},
                {"invoice_id": "A101", "status": "open"},
            ]
        )
        monkeypatch.setattr(
            InvoiceListView,
            "oracle_adapter_provider",
            staticmethod(lambda: adapter),
        )

        response = admin_client.get("/api/invoices/?status=paid&limit=2")

        assert response.status_code == 200
        assert response.json() == {
            "count": 2,
            "results": [
                {
                    "invoice_id": "A100",
                    "status": "PAID",
                    "status_label": "Paid",
                    "is_closed": True,
                },
                {
                    "invoice_id": "A101",
                    "status": "OPEN",
                    "status_label": "Open",
                    "is_closed": False,
                },
            ],
        }
        assert len(adapter.calls) == 1
        assert adapter.calls[0][1] == {"status": "PAID", "max_rows": 2}

    @pytest.mark.django_db
    def test_viewer_returns_200(
        self,
        viewer_client: Client,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Viewer users can access read-only invoice endpoint."""

        adapter = _StubOracleAdapter([])
        monkeypatch.setattr(
            InvoiceListView,
            "oracle_adapter_provider",
            staticmethod(lambda: adapter),
        )

        response = viewer_client.get("/api/invoices/")

        assert response.status_code == 200
        assert response.json() == {"count": 0, "results": []}
        assert adapter.calls[0][1] == {"status": None, "max_rows": 100}

    def test_unauthenticated_returns_401(self, unauthenticated_client: Client) -> None:
        """Unauthenticated request is denied by authz middleware."""

        response = unauthenticated_client.get("/api/invoices/")

        assert response.status_code == 401

    @pytest.mark.django_db
    def test_unauthorized_returns_403(self, unauthorized_client: Client) -> None:
        """Authenticated user without mapped role gets 403."""

        response = unauthorized_client.get("/api/invoices/")

        assert response.status_code == 403
        assert (
            response.json()["detail"]
            == "You do not have permission to perform this action."
        )

    @pytest.mark.django_db
    def test_invalid_limit_returns_400_and_skips_adapter(
        self,
        admin_client: Client,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Query validation errors return 400 via global exception handler."""

        adapter = _StubOracleAdapter([])
        monkeypatch.setattr(
            InvoiceListView,
            "oracle_adapter_provider",
            staticmethod(lambda: adapter),
        )

        response = admin_client.get("/api/invoices/?limit=0")

        assert response.status_code == 400
        payload = response.json()
        assert "limit" in payload
        assert "request_id" in payload
        assert adapter.calls == []

    @pytest.mark.django_db
    def test_invalid_status_returns_400_and_skips_adapter(
        self,
        admin_client: Client,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Invalid status filter format returns 400 from query serializer."""

        adapter = _StubOracleAdapter([])
        monkeypatch.setattr(
            InvoiceListView,
            "oracle_adapter_provider",
            staticmethod(lambda: adapter),
        )

        response = admin_client.get("/api/invoices/?status=bad/status")

        assert response.status_code == 400
        payload = response.json()
        assert "status" in payload
        assert "request_id" in payload
        assert adapter.calls == []

    @pytest.mark.django_db
    def test_response_has_private_cache_headers(
        self,
        admin_client: Client,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Invoice endpoint uses private/no-cache policy plus CSP middleware."""

        adapter = _StubOracleAdapter([])
        monkeypatch.setattr(
            InvoiceListView,
            "oracle_adapter_provider",
            staticmethod(lambda: adapter),
        )

        response = admin_client.get("/api/invoices/")

        cache_control = response.headers.get("Cache-Control", "")
        assert "private" in cache_control
        assert "no-cache" in cache_control
        assert "default-src 'none'" in response.headers.get(
            "Content-Security-Policy", ""
        )

    @pytest.mark.django_db
    def test_post_not_allowed(
        self,
        admin_client: Client,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Only GET is supported on invoice list endpoint."""

        adapter = _StubOracleAdapter([])
        monkeypatch.setattr(
            InvoiceListView,
            "oracle_adapter_provider",
            staticmethod(lambda: adapter),
        )

        response = admin_client.post("/api/invoices/")

        assert response.status_code == 405

    @pytest.mark.django_db
    def test_returns_429_when_throttled(
        self,
        admin_client: Client,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Second rapid request returns standard throttle envelope."""

        cache.clear()
        adapter = _StubOracleAdapter([])
        monkeypatch.setattr(
            InvoiceListView,
            "oracle_adapter_provider",
            staticmethod(lambda: adapter),
        )
        monkeypatch.setattr(InvoiceListView, "_throttle_rate", "1/minute")

        first = admin_client.get("/api/invoices/")
        second = admin_client.get("/api/invoices/")

        assert first.status_code == 200
        assert second.status_code == 429
        payload = second.json()
        assert "throttled" in payload["detail"].lower()
        assert "request_id" in payload

    @pytest.mark.django_db
    def test_throttle_includes_retry_after(
        self,
        admin_client: Client,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """429 response includes Retry-After header."""

        cache.clear()
        adapter = _StubOracleAdapter([])
        monkeypatch.setattr(
            InvoiceListView,
            "oracle_adapter_provider",
            staticmethod(lambda: adapter),
        )
        monkeypatch.setattr(InvoiceListView, "_throttle_rate", "1/minute")

        admin_client.get("/api/invoices/")
        response = admin_client.get("/api/invoices/")

        assert response.status_code == 429
        assert response["Retry-After"].isdigit()
