"""Custom DRF exception handler.

Provides a single, consistent error envelope for every 4xx and 5xx response:

    {"detail": "...", "request_id": "<uuid>"}

Delegates to DRF's built-in handler first so all ``APIException`` subclasses,
``Http404``, and Django's ``PermissionDenied`` are handled automatically.
Unhandled exceptions are logged with full tracebacks at ``ERROR`` level and
surfaced to the client as a safe 500 response — no internal details leak.
"""

from __future__ import annotations

import logging
from typing import Any

from django.http import JsonResponse
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import exception_handler

from api.middleware.request_id import request_id_var
from api.security_logging import build_security_event_fields

logger = logging.getLogger(__name__)


def api_exception_handler(
    exc: Exception, context: dict[str, Any]
) -> Response | JsonResponse:
    """Handle all exceptions raised within DRF views.

    Args:
        exc: The exception raised by the view.
        context: DRF context dict containing ``request``, ``view``, etc.

    Returns:
        A ``Response`` or ``JsonResponse`` with ``detail`` and ``request_id``.
    """
    request: Request | None = context.get("request")
    request_id = getattr(request, "request_id", None) or request_id_var.get()

    response = exception_handler(exc, context)

    if response is not None:
        if isinstance(exc, ValidationError):
            logger.warning(
                "request validation failed",
                extra=build_security_event_fields(
                    request,
                    event_type="INPUT_VALIDATION_FAILURE",
                    action_attempted="validate request data",
                    result="failure",
                    status_code=response.status_code,
                ),
            )
        response.data["request_id"] = request_id
        return response

    logger.exception(
        "unhandled exception",
        extra=build_security_event_fields(
            request,
            event_type="UNHANDLED_EXCEPTION",
            action_attempted="execute request",
            result="failure",
            status_code=500,
            exception_type=exc.__class__.__name__,
            request_id=request_id,
        ),
    )
    return JsonResponse(
        {"detail": "An unexpected error occurred.", "request_id": request_id},
        status=500,
    )
