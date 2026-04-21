"""User information endpoint.

Returns authenticated user identity and role information.
"""

from __future__ import annotations

from typing import Any

from rest_framework.response import Response

from api.caching import cache_private
from api.constants import ROLE_ADMIN, ROLE_VIEWER
from api.permissions import authz_roles
from api.serializers import UserSerializer
from api.throttling import throttle
from api.views.base import BaseAPIView


@throttle("30/minute")
@cache_private
@authz_roles(ROLE_ADMIN, ROLE_VIEWER)
class UserView(BaseAPIView):
    """Return the authenticated user's identity and application roles.

    Only GET is supported. Django's View dispatch returns 405 Method Not
    Allowed automatically for any other method — no manual check required.
    """

    serializer_class = UserSerializer

    def get(self, request: Any) -> Response:
        """Return username and resolved application roles."""
        user = self.get_request_user(request)
        payload: dict[str, Any] = {
            "username": user.get_username(),
            "roles": list(getattr(user, "roles", [])),
        }
        serializer = UserSerializer(payload)
        return Response(serializer.data)
