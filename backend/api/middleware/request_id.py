"""Request-ID tracking middleware.

Generates and attaches unique identifiers to each request for distributed
tracing and debugging.
"""
from __future__ import annotations

import uuid
from typing import Any, Callable

from django.http import HttpRequest, HttpResponse
from django.utils.deprecation import MiddlewareMixin


class RequestIdMiddleware(MiddlewareMixin):
    """Middleware that generates and tracks unique request IDs.
    
    Generates a UUID4 for each request and attaches it to:
    - request.request_id (attribute)
    - X-Request-ID response header (for client access)
    
    This enables distributed tracing and debugging across logs.
    """

    def process_request(self, request: HttpRequest) -> None:
        """Generate request ID and attach to request object.
        
        Args:
            request: The incoming HTTP request.
        """
        # Generate a new UUID4 for this request
        request_id = str(uuid.uuid4())
        # Attach to request object for downstream access
        request.request_id = request_id  # type: ignore[attr-defined]

    def process_response(
        self, request: HttpRequest, response: HttpResponse
    ) -> HttpResponse:
        """Attach request ID to response header.
        
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
        return response

