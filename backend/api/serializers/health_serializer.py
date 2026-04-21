"""Serializers for health endpoint responses."""

from __future__ import annotations

from rest_framework import serializers


class HealthSerializer(serializers.Serializer):
    """Serializer for the health check response payload."""

    status = serializers.CharField()
    version = serializers.CharField()
    uptime_seconds = serializers.IntegerField(min_value=0)
