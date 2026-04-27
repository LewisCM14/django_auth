"""Content Security Policy middleware."""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Any, Callable, cast

from asgiref.sync import iscoroutinefunction, markcoroutinefunction
from django.conf import settings
from django.http import HttpRequest, HttpResponse


class ContentSecurityPolicyMiddleware:
    """Attach a strict Content-Security-Policy header to every response."""

    def __init__(self, get_response: Callable[[HttpRequest], Any]) -> None:
        self.get_response = get_response
        self.is_async = iscoroutinefunction(get_response)
        if self.is_async:
            markcoroutinefunction(self)

    def __call__(self, request: HttpRequest) -> HttpResponse | Awaitable[HttpResponse]:
        """Attach CSP header in sync or async middleware chains."""
        if self.is_async:
            return self.__acall__(request)
        response = cast(HttpResponse, self.get_response(request))
        return self.process_response(request, response)

    async def __acall__(self, request: HttpRequest) -> HttpResponse:
        """Attach CSP header in async middleware chains."""
        response = cast(HttpResponse, await self.get_response(request))
        return self.process_response(request, response)

    def process_response(
        self, request: HttpRequest, response: HttpResponse
    ) -> HttpResponse:
        del request
        response.headers.setdefault(
            "Content-Security-Policy", settings.CONTENT_SECURITY_POLICY
        )
        return response
