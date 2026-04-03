"""User information endpoint.

Returns authenticated user identity and role information.
"""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest, JsonResponse
from django.views import View

from api.constants import ROLE_ADMIN, ROLE_VIEWER
from api.permissions import authz_roles
from api.serializers import UserSerializer


@authz_roles(ROLE_ADMIN, ROLE_VIEWER)
class UserView(View):
    """Return the authenticated user's identity and application roles.

    Only GET is supported. Django's View dispatch returns 405 Method Not
    Allowed automatically for any other method — no manual check required.
    """

    def get(self, request: HttpRequest) -> JsonResponse:
        """Return username and resolved application roles."""
        user = request.user
        payload: dict[str, Any] = {
            "username": user.get_username(),
            "roles": list(getattr(user, "roles", [])),
        }
        serializer = UserSerializer(payload)
        response = JsonResponse(serializer.data)
        response["Cache-Control"] = "private, no-cache"
        return response
