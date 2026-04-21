"""Shared base class for application API views."""

from __future__ import annotations

from typing import Any

from rest_framework.views import APIView

from api.request_user import get_request_user


class BaseAPIView(APIView):
    """Thin base class for project API endpoints.

    Keeps shared request-user resolution in one place without replacing the
    decorator-enforcement middleware or the Spectacular base classes used by
    schema/docs wrappers.
    """

    @staticmethod
    def get_request_user(request: Any) -> Any:
        """Return the middleware-resolved user for a request object."""

        return get_request_user(request)
