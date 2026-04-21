"""Health check endpoint.

Provides a simple status endpoint for monitoring and load balancer checks.
Returns service status, API version, and process uptime.
"""

from __future__ import annotations

import time
from typing import Any

from django.conf import settings
from rest_framework.response import Response

from api.caching import cache_public
from api.permissions import authz_public
from api.serializers import HealthSerializer
from api.throttling import throttle
from api.views.base import BaseAPIView


PROCESS_START_MONOTONIC = time.monotonic()


@throttle("60/minute")
@cache_public(max_age=5)
@authz_public
class HealthView(BaseAPIView):
    """Health check endpoint returning service status.

    This endpoint is unauthenticated and publicly accessible for use by
    load balancers, uptime monitors, and health checks. It reports the
    configured API version and the current process uptime.
    """

    serializer_class = HealthSerializer

    def get(self, request: Any) -> Response:
        """Return health status.

        Args:
            request: The HTTP request object.

        Returns:
            Response with status, version, uptime, and HTTP 200 status code.
        """
        payload = {
            "status": "ok",
            "version": settings.API_VERSION,
            "uptime_seconds": int(time.monotonic() - PROCESS_START_MONOTONIC),
        }
        return Response(payload)
