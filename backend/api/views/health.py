"""Health check endpoint.

Provides a simple status endpoint for monitoring and load balancer checks.
"""

from __future__ import annotations

from typing import Any

from rest_framework.response import Response
from rest_framework.views import APIView

from api.permissions import authz_public


@authz_public
class HealthView(APIView):
    """Health check endpoint returning service status.

    This endpoint is unauthenticated and publicly accessible for use by
    load balancers, uptime monitors, and health checks.
    """

    def get(self, request: Any) -> Response:
        """Return health status.

        Args:
            request: The HTTP request object.

        Returns:
            Response with status=ok and HTTP 200 status code.
        """
        return Response({"status": "ok"})
