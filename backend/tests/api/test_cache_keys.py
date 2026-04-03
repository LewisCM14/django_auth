"""Tests for centralized cache key builders in api.cache_keys."""

from __future__ import annotations

from api.cache_keys import adapter_key, service_key, view_key


class TestAdapterKey:
    """Tests for adapter-layer cache key construction."""

    def test_builds_expected_pattern(self) -> None:
        """Adapter key includes normalized source, resource, and identifier."""
        assert (
            adapter_key("ERP", "Invoice", "INV-2024-001")
            == "adapter:erp:invoice:inv-2024-001"
        )

    def test_normalizes_spaces_and_colons(self) -> None:
        """Adapter key components are normalized for stability."""
        assert (
            adapter_key("External Source", "Order:Items", "A B:C")
            == "adapter:external_source:order_items:a_b_c"
        )


class TestViewKey:
    """Tests for view-layer cache key construction."""

    def test_is_deterministic_for_same_input(self) -> None:
        """Equivalent mappings generate the same key regardless of insertion order."""
        first = view_key("order_list", {"page": 1, "status": "open"})
        second = view_key("order_list", {"status": "open", "page": 1})
        assert first == second

    def test_changes_when_params_change(self) -> None:
        """Different query params produce different hashes and keys."""
        first = view_key("order_list", {"page": 1})
        second = view_key("order_list", {"page": 2})
        assert first != second


class TestServiceKey:
    """Tests for service-layer cache key construction."""

    def test_builds_expected_prefix(self) -> None:
        """Service key starts with normalized domain and operation components."""
        key = service_key("Reporting", "Monthly Summary", {"month": "2026-03"})
        assert key.startswith("service:reporting:monthly_summary:")

    def test_changes_when_params_change(self) -> None:
        """Parameter changes produce a different service key hash."""
        first = service_key("reporting", "monthly_summary", {"month": "2026-03"})
        second = service_key("reporting", "monthly_summary", {"month": "2026-04"})
        assert first != second
