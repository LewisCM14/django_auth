"""User information endpoint.

Returns authenticated user identity and role information.
"""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest, HttpResponseNotAllowed, JsonResponse

from api.constants import ROLE_ADMIN, ROLE_VIEWER
from api.permissions import authz_roles
from api.serializers import UserSerializer


@authz_roles(ROLE_ADMIN, ROLE_VIEWER)
def UserView(request: HttpRequest) -> JsonResponse | HttpResponseNotAllowed:
    """Return the authenticated user's identity and application roles."""
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])

    user = request.user
    payload: dict[str, Any] = {
        "username": user.get_username(),
        "roles": list(getattr(user, "roles", [])),
    }
    serializer = UserSerializer(payload)
    return JsonResponse(serializer.data)
