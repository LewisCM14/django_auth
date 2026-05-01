"""Serializer contracts for the Oracle-backed invoice list endpoint.

The query serializer normalizes and validates incoming filters.
Response serializers define the stable API envelope returned by the view.
"""

from __future__ import annotations

import re

from rest_framework import serializers


# Status tokens are constrained to a safe, uppercase-friendly identifier set.
_STATUS_FILTER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]{0,31}$", re.ASCII)


class InvoiceListQuerySerializer(serializers.Serializer):
    """Validate and normalize query parameters for invoice list reads.

    Fields:
        status: Optional invoice status filter (max 32 chars).
        limit: Maximum number of rows to return, defaulting to 100.
    """

    status = serializers.CharField(required=False, allow_blank=False, max_length=32)
    limit = serializers.IntegerField(
        required=False,
        min_value=1,
        max_value=500,
        default=100,
    )

    def validate_status(self, value: str) -> str:
        """Normalize and validate the optional status filter.

        Args:
            value: Raw status value from query parameters.

        Returns:
            Uppercased, trimmed status string.

        Raises:
            ValidationError: If the status does not match the allowlisted
                pattern.
        """

        normalized = value.strip().upper()
        if not _STATUS_FILTER_RE.fullmatch(normalized):
            raise serializers.ValidationError(
                "status must match ^[A-Za-z_][A-Za-z0-9_-]{0,31}$."
            )
        return normalized


class InvoiceRecordSerializer(serializers.Serializer):
    """Serializer for a normalized invoice record in the list response."""

    invoice_id = serializers.CharField()
    status = serializers.CharField()
    status_label = serializers.CharField()
    is_closed = serializers.BooleanField()


class InvoiceListResponseSerializer(serializers.Serializer):
    """Top-level response envelope for invoice list endpoint results."""

    count = serializers.IntegerField(min_value=0)
    results = InvoiceRecordSerializer(many=True)
