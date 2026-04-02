"""User-related serializers.

Defines serializers for user identity and role payloads returned by API endpoints.
"""

from __future__ import annotations

from rest_framework import serializers


class UserSerializer(serializers.Serializer):
    """Serializer for authenticated user identity and role payloads.

    This serializer defines the response contract for endpoints that return
    the current user's identity and assigned application roles.
    """

    username = serializers.CharField()
    roles = serializers.ListField(child=serializers.CharField())
