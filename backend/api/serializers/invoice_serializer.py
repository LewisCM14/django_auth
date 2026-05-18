"""Serializer contracts for the Oracle-backed equipment serial endpoint."""

from __future__ import annotations

from rest_framework import serializers


class EquipmentSerialQuerySerializer(serializers.Serializer):
    """Validate and normalize query parameters for equipment serial reads."""

    name = serializers.CharField(required=True, allow_blank=False, max_length=200)

    def validate_name(self, value: str) -> str:
        return value.strip()


class EquipmentSerialListResponseSerializer(serializers.Serializer):
    """Top-level response envelope for equipment serial list endpoint results."""

    count = serializers.IntegerField(min_value=0)
    results = serializers.ListField(child=serializers.CharField())
