"""Authentication middleware.

Handles user identity resolution in both development (mock user injection)
and production (IIS/Windows authentication) modes.
"""

from __future__ import annotations

import logging
import os
from typing import Callable

from django.contrib.auth.models import AnonymousUser
from django.contrib.auth.models import User
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpRequest, HttpResponse
from django.utils.decorators import sync_and_async_middleware

from api.validation import validate_username
from api.security_logging import build_security_event_fields

logger = logging.getLogger(__name__)


@sync_and_async_middleware
class AuthenticationMiddleware:
    """Middleware that authenticates requests in dev or IIS mode.

    In dev mode (AUTH_MODE=dev):
    - Injects a mock user from DEV_USER_IDENTITY environment variable
    - Defaults to 'dev_admin' if not configured
    - Automatically creates/retrieves a Django User object

    In IIS mode (AUTH_MODE=iis):
    - Reads the REMOTE_USER header provided by IIS
    - Creates or retrieves a Django User object via get_or_create
    - Attaches AnonymousUser when REMOTE_USER is not present
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        """Initialize the middleware.

        Args:
            get_response: The next middleware or view in the chain.
        """
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Process the request and response.

        Args:
            request: The HTTP request object.

        Returns:
            The HTTP response from the next middleware or view.
        """
        self.process_request(request)
        response = self.get_response(request)
        return response

    def process_request(self, request: HttpRequest) -> None:
        """Authenticate the request and attach user to request object.

        In dev mode:
        - Reads DEV_USER_IDENTITY from environment (defaults to 'dev_admin')
        - Creates or retrieves a Django User object with that username
        - Attaches the User to request.user

        In IIS mode:
        - Reads REMOTE_USER from request.META (set by IIS)
        - Creates or retrieves a Django User with that username
        - Attaches AnonymousUser if REMOTE_USER is not present

        Args:
            request: The HTTP request object to authenticate.
        """
        auth_mode = os.getenv("AUTH_MODE", "iis")
        anonymous_user = AnonymousUser()
        request.user = anonymous_user
        request._cached_user = anonymous_user  # type: ignore[attr-defined]  # HttpRequest gains _cached_user dynamically at runtime; Django's stubs do not declare it.

        if auth_mode == "dev":
            # Development mode: inject mock user
            dev_user_identity = os.getenv("DEV_USER_IDENTITY", "dev_admin")
            try:
                validate_username(dev_user_identity, allow_domain_prefix=False)
            except ImproperlyConfigured:
                logger.warning(
                    "invalid DEV_USER_IDENTITY configuration",
                    extra=build_security_event_fields(
                        request,
                        event_type="INPUT_VALIDATION_FAILURE",
                        action_attempted="validate DEV_USER_IDENTITY",
                        result="failure",
                        user_identifier="anonymous",
                    ),
                )
                raise ImproperlyConfigured(
                    "DEV_USER_IDENTITY is invalid. Expected 1-64 characters from [A-Za-z0-9._-]."
                )
            user, _ = User.objects.get_or_create(username=dev_user_identity)
            request.user = user
            # Django's AuthenticationMiddleware stores this attribute dynamically at runtime.
            # The HttpRequest type stub does not declare it, so this ignore is intentional.
            request._cached_user = user  # type: ignore[attr-defined]
            logger.info(
                "authentication succeeded",
                extra=build_security_event_fields(
                    request,
                    event_type="AUTHENTICATION_SUCCESS",
                    action_attempted="authenticate dev user",
                    result="success",
                    user_identifier=dev_user_identity,
                ),
            )
        else:
            # IIS mode: read REMOTE_USER and create/retrieve user
            remote_user = request.META.get("REMOTE_USER") or request.META.get(
                "HTTP_REMOTE_USER"
            )
            if remote_user:
                try:
                    validate_username(remote_user, allow_domain_prefix=True)
                except ImproperlyConfigured:
                    # Invalid REMOTE_USER values are treated as anonymous to fail closed.
                    logger.warning(
                        "invalid REMOTE_USER rejected",
                        extra=build_security_event_fields(
                            request,
                            event_type="INPUT_VALIDATION_FAILURE",
                            action_attempted="validate REMOTE_USER",
                            result="failure",
                            user_identifier="anonymous",
                        ),
                    )
                    request.user = anonymous_user
                    request._cached_user = anonymous_user  # type: ignore[attr-defined]
                    return
                user, _ = User.objects.get_or_create(username=remote_user)
                request.user = user
                # Same rationale as above: _cached_user exists at runtime but is not typed on HttpRequest.
                request._cached_user = user  # type: ignore[attr-defined]
                logger.info(
                    "authentication succeeded",
                    extra=build_security_event_fields(
                        request,
                        event_type="AUTHENTICATION_SUCCESS",
                        action_attempted="authenticate REMOTE_USER",
                        result="success",
                        user_identifier=remote_user,
                    ),
                )
