"""Serializer contracts for the Oracle-backed equipment serial endpoint."""

from __future__ import annotations

from rest_framework import serializers


class EquipmentSerialListResponseSerializer(serializers.Serializer):
    """Top-level response envelope for equipment serial list endpoint results."""

    count = serializers.IntegerField(min_value=0)
    results = serializers.ListField(child=serializers.CharField())
