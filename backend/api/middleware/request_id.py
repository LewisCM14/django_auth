"""Request-ID tracking middleware.

Generates and attaches unique identifiers to each request for distributed
tracing and debugging. Also provides a context variable and logging filter
so all log records automatically carry the correlation ID.
"""

from __future__ import annotations

import contextvars
import logging
import time
import uuid

from django.http import HttpRequest, HttpResponse
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)

# Module-level context variable holding the current request ID.
# Defaults to "-" when no request is in flight (e.g. management commands,
# startup code) so log records always have a well-defined request_id field.
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)


class RequestIdFilter(logging.Filter):
    """Logging filter that injects the current request ID into every log record.

    Attach this filter to all handlers in the LOGGING config so that every
    log line — from middleware, views, services, or Django internals —
    automatically carries the correlation ID without any manual passing.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Inject request_id from the context variable into the log record.

        Args:
            record: The log record to enrich.

        Returns:
            Always True — this filter never suppresses records.
        """
        record.request_id = request_id_var.get()
        return True


class RequestIdMiddleware(MiddlewareMixin):
    """Middleware that generates and tracks unique request IDs.

    Generates a UUID4 for each request and attaches it to:
    - request.request_id (attribute)
    - request_id_var (contextvars.ContextVar, for logging correlation)
    - X-Request-ID response header (for client access)

    This enables distributed tracing and debugging across logs.
    """

    def process_request(self, request: HttpRequest) -> None:
        """Generate request ID, attach to request object, and set context variable.

        Args:
            request: The incoming HTTP request.
        """
        # Generate a new UUID4 for this request
        request_id = str(uuid.uuid4())
        # Attach to request object for downstream access
        request.request_id = request_id  # type: ignore[attr-defined]  # HttpRequest stubs don't allow dynamic attributes
        request._start_time = time.monotonic()  # type: ignore[attr-defined]  # HttpRequest stubs don't allow dynamic attributes
        # Store in context variable so all loggers can read it without
        # explicit passing through call chains.
        request_id_var.set(request_id)

    def process_response(
        self, request: HttpRequest, response: HttpResponse
    ) -> HttpResponse:
        """Attach request ID to response header and reset the context variable.

        Args:
            request: The HTTP request object.
            response: The HTTP response object.

        Returns:
            The response object with X-Request-ID header set.
        """
        # Retrieve request ID from request object
        request_id = getattr(request, "request_id", str(uuid.uuid4()))
        # Attach to response header
        response["X-Request-ID"] = request_id
        # Compute request duration in milliseconds.
        start: float = getattr(request, "_start_time", time.monotonic())
        duration_ms: float = (time.monotonic() - start) * 1000
        # Resolve the username — authenticated user or anonymous.
        user = getattr(request, "user", None)
        username: str = user.get_username() if user and user.is_authenticated else "anonymous"
        logger.info(
            "%s %s %s %.1fms %s",
            request.method,
            request.path,
            response.status_code,
            duration_ms,
            username,
        )
        # Reset context variable so the "-" default applies cleanly to any
        # work that runs after this response (e.g. background tasks, signals).
        request_id_var.set("-")
        return response
