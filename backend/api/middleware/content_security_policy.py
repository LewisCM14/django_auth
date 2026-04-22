"""Content Security Policy middleware."""

from __future__ import annotations

from typing import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.utils.decorators import sync_and_async_middleware


@sync_and_async_middleware
class ContentSecurityPolicyMiddleware:
    """Attach a strict Content-Security-Policy header to every response."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        response.headers.setdefault(
            "Content-Security-Policy", settings.CONTENT_SECURITY_POLICY
        )
        return response
