"""Authentication middleware.

Handles user identity resolution in both development (mock user injection)
and production (IIS/Windows authentication) modes.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import os
import sys
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Any, Callable, Protocol, cast

from asgiref.sync import iscoroutinefunction, markcoroutinefunction, sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth.models import User
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpRequest, HttpResponse

from api.security_logging import build_security_event_fields
from api.validation import validate_username

logger = logging.getLogger(__name__)

WINDOWS_AUTH_TOKEN_META_KEY = "HTTP_X_IIS_WINDOWSAUTHTOKEN"


class _Win32ApiModule(Protocol):
    def GetUserName(self) -> str: ...

    def CloseHandle(self, handle: int) -> None: ...


class _Win32SecurityModule(Protocol):
    def ImpersonateLoggedOnUser(self, handle: int) -> None: ...

    def RevertToSelf(self) -> None: ...


@dataclass(frozen=True)
class WindowsAuthIdentityResolver:
    """Resolve IIS Windows auth token headers to a Windows username."""

    def resolve(self, token_header_value: str) -> str | None:
        """Resolve a username from the forwarded IIS auth token.

        Returns ``None`` when token parsing or impersonation fails.
        """
        token_handle = _parse_token_handle(token_header_value)
        if token_handle is None:
            return None

        modules = _load_pywin32_modules()
        if modules is None:
            return None

        win32api, win32security = modules
        username: str | None = None
        impersonation_started = False

        try:
            win32security.ImpersonateLoggedOnUser(token_handle)
            impersonation_started = True
            username = win32api.GetUserName()
        except OSError:
            return None
        finally:
            if impersonation_started:
                try:
                    win32security.RevertToSelf()
                except OSError:
                    logger.exception("failed to revert Windows impersonation context")
            try:
                win32api.CloseHandle(token_handle)
            except OSError:
                logger.exception("failed to close Windows auth token handle")

        return username


def _parse_token_handle(token_header_value: str) -> int | None:
    """Convert IIS token string to a Windows handle int."""
    if not token_header_value.strip():
        return None

    try:
        return int(token_header_value, 16)
    except ValueError:
        return None


def _load_pywin32_modules() -> tuple[_Win32ApiModule, _Win32SecurityModule] | None:
    """Load pywin32 modules on Windows hosts.

    Returns ``None`` on non-Windows hosts or when pywin32 is unavailable.
    """
    if not sys.platform.startswith("win"):
        return None

    if importlib.util.find_spec("win32api") is None:
        return None
    if importlib.util.find_spec("win32security") is None:
        return None

    win32api = cast(_Win32ApiModule, importlib.import_module("win32api"))
    win32security = cast(_Win32SecurityModule, importlib.import_module("win32security"))
    return win32api, win32security


class AuthenticationMiddleware:
    """Middleware that authenticates requests in dev or IIS mode.

    In dev mode (AUTH_MODE=dev):
    - Injects a mock user from DEV_USER_IDENTITY environment variable
    - Defaults to 'dev_admin' if not configured
    - Automatically creates/retrieves a Django User object

    In IIS mode (AUTH_MODE=iis):
    - Reads X-IIS-WindowsAuthToken provided by IIS HttpPlatformHandler
    - Resolves a Windows username by impersonating that token handle
    - Creates or retrieves a Django User object via get_or_create
    - Attaches AnonymousUser when token/header resolution fails
    """

    def __init__(self, get_response: Callable[[HttpRequest], Any]) -> None:
        """Initialize the middleware.

        Args:
            get_response: The next middleware or view in the chain.
        """
        self.get_response = get_response
        self.is_async = iscoroutinefunction(get_response)
        self.identity_resolver = WindowsAuthIdentityResolver()
        if self.is_async:
            markcoroutinefunction(self)

    def __call__(self, request: HttpRequest) -> HttpResponse | Awaitable[HttpResponse]:
        """Dispatch request handling for sync or async middleware chains."""
        if self.is_async:
            return self.__acall__(request)
        self.process_request(request)
        return cast(HttpResponse, self.get_response(request))

    async def __acall__(self, request: HttpRequest) -> HttpResponse:
        """Run authentication in a thread and continue async middleware chain."""
        await sync_to_async(self.process_request, thread_sensitive=True)(request)
        return cast(HttpResponse, await self.get_response(request))

    def process_request(self, request: HttpRequest) -> None:
        """Authenticate the request and attach user to request object."""
        auth_mode = os.getenv("AUTH_MODE", "iis")
        anonymous_user = AnonymousUser()
        request.user = anonymous_user
        request._cached_user = anonymous_user  # type: ignore[attr-defined]

        if auth_mode == "dev":
            self._authenticate_dev_user(request)
            return

        self._authenticate_iis_user(request, anonymous_user)

    def _authenticate_dev_user(self, request: HttpRequest) -> None:
        """Authenticate using development identity environment variable."""
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

    def _authenticate_iis_user(
        self, request: HttpRequest, anonymous_user: AnonymousUser
    ) -> None:
        """Authenticate using X-IIS-WindowsAuthToken forwarded by IIS."""
        raw_token = request.META.get(WINDOWS_AUTH_TOKEN_META_KEY)
        if not raw_token:
            return

        remote_user = self.identity_resolver.resolve(raw_token)
        if remote_user is None:
            logger.warning(
                "invalid X-IIS-WindowsAuthToken rejected",
                extra=build_security_event_fields(
                    request,
                    event_type="INPUT_VALIDATION_FAILURE",
                    action_attempted="resolve X-IIS-WindowsAuthToken",
                    result="failure",
                    user_identifier="anonymous",
                ),
            )
            request.user = anonymous_user
            request._cached_user = anonymous_user  # type: ignore[attr-defined]
            return

        try:
            validate_username(remote_user, allow_domain_prefix=True)
        except ImproperlyConfigured:
            logger.warning(
                "resolved Windows identity rejected by username validator",
                extra=build_security_event_fields(
                    request,
                    event_type="INPUT_VALIDATION_FAILURE",
                    action_attempted="validate Windows username",
                    result="failure",
                    user_identifier="anonymous",
                ),
            )
            request.user = anonymous_user
            request._cached_user = anonymous_user  # type: ignore[attr-defined]
            return

        user, _ = User.objects.get_or_create(username=remote_user)
        request.user = user
        request._cached_user = user  # type: ignore[attr-defined]
        logger.info(
            "authentication succeeded",
            extra=build_security_event_fields(
                request,
                event_type="AUTHENTICATION_SUCCESS",
                action_attempted="authenticate X-IIS-WindowsAuthToken",
                result="success",
                user_identifier=remote_user,
            ),
        )
