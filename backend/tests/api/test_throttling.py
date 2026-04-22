"""Tests for rate-limiting utilities in api.throttling."""

from __future__ import annotations

import logging
import json
from typing import Any, cast

import pytest
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.test import RequestFactory
from django.views import View
from rest_framework.views import APIView

from api.permissions import authz_roles
from api.throttling import (
    THROTTLE_RATE_ATTR,
    RemoteUserRateThrottle,
    _throttle_detail,
    _throttle_wait_seconds,
    throttle,
    throttle_exempt,
)


class TestRemoteUserRateThrottle:
    """Unit tests for cache-key generation and rate resolution."""

    @pytest.fixture(autouse=True)
    def clear_cache(self) -> None:
        """Clear cache to keep throttle state isolated across tests."""
        cache.clear()

    def test_authenticated_user_cache_key_contains_username(self) -> None:
        """Cache key uses authenticated username identity when available."""
        request = RequestFactory().get("/api/user/")
        request.user = cast(Any, _AuthenticatedUser("DOMAIN\\admin_user"))

        throttle_instance = RemoteUserRateThrottle()

        @throttle("10/minute")
        class StubView(View):
            """View stub for testing throttle key generation."""

            def get(self, request: HttpRequest) -> JsonResponse:
                """Return a success payload."""
                del request
                return JsonResponse({"ok": True})

        view_instance = StubView()
        throttle_instance.allow_request(request, view_instance)

        assert throttle_instance.get_cache_key(request, view_instance) is not None  # type: ignore[arg-type]  # testing with HttpRequest; production code accepts both via cast
        key = throttle_instance.get_cache_key(request, view_instance)  # type: ignore[arg-type]  # same as above
        assert key is not None
        assert "DOMAIN\\admin_user" in key

    def test_unauthenticated_request_cache_key_falls_back_to_ip(self) -> None:
        """Cache key uses request IP when no authenticated user exists."""
        request = RequestFactory().get("/api/health/", REMOTE_ADDR="10.0.0.1")

        throttle_instance = RemoteUserRateThrottle()

        @throttle("10/minute")
        class StubView(View):
            """View stub for testing throttle key generation."""

            def get(self, request: HttpRequest) -> JsonResponse:
                """Return a success payload."""
                del request
                return JsonResponse({"ok": True})

        view_instance = StubView()
        throttle_instance.allow_request(request, view_instance)

        key = throttle_instance.get_cache_key(request, view_instance)  # type: ignore[arg-type]  # testing with HttpRequest; signature expects DRF Request
        assert key is not None
        assert "10.0.0.1" in key

    def test_cache_key_scope_uses_view_class_name(self) -> None:
        """Cache key scope is derived from the view class name."""
        request = RequestFactory().get("/api/schema/")

        throttle_instance = RemoteUserRateThrottle()

        @throttle("10/minute")
        class MyCustomView(View):
            """View stub for testing scope derivation."""

            def get(self, request: HttpRequest) -> JsonResponse:
                """Return a success payload."""
                del request
                return JsonResponse({"ok": True})

        view_instance = MyCustomView()
        throttle_instance.allow_request(request, view_instance)

        key = throttle_instance.get_cache_key(request, view_instance)  # type: ignore[arg-type]  # testing with HttpRequest; signature expects DRF Request
        assert key is not None
        assert "MyCustomView" in key

    def test_allow_request_returns_true_when_no_rate(self) -> None:
        """Requests pass through when view has no _throttle_rate attribute."""
        request = RequestFactory().get("/")

        throttle_instance = RemoteUserRateThrottle()
        view_stub = type("PlainView", (), {})()

        assert throttle_instance.allow_request(request, view_stub) is True


class TestThrottleDecoratorOnDRFView:
    """Tests for @throttle applied to DRF APIView subclasses."""

    @pytest.fixture(autouse=True)
    def clear_cache(self) -> None:
        """Clear cache to keep throttle state isolated across tests."""
        cache.clear()

    def test_sets_throttle_classes_and_rate(self) -> None:
        """Decorator sets throttle_classes and _throttle_rate on APIView."""

        @throttle("60/minute")
        class StubAPIView(APIView):
            """DRF view stub for testing decorator wiring."""

        assert StubAPIView.throttle_classes == [RemoteUserRateThrottle]
        assert getattr(StubAPIView, "_throttle_rate") == "60/minute"


class TestThrottleDecoratorOnDjangoView:
    """Tests for @throttle applied to Django View subclasses."""

    @pytest.fixture(autouse=True)
    def clear_cache(self) -> None:
        """Clear cache to keep throttle state isolated across tests."""
        cache.clear()

    def test_allows_request_under_limit(self) -> None:
        """Request under configured limit reaches the wrapped view."""

        @throttle("10/minute")
        class DecoratedView(View):
            """Simple view used for throttle decorator tests."""

            def get(self, request: HttpRequest) -> JsonResponse:
                """Return a success payload."""
                del request
                return JsonResponse({"ok": True})

        response = DecoratedView.as_view()(RequestFactory().get("/decorated/"))

        assert response.status_code == 200
        assert isinstance(response, HttpResponse)
        assert json.loads(response.content) == {"ok": True}

    def test_blocks_request_over_limit(self) -> None:
        """Second request in same window is blocked with 429 response."""

        @throttle("1/minute")
        class DecoratedView(View):
            """Simple view used for throttle decorator tests."""

            def get(self, request: HttpRequest) -> JsonResponse:
                """Return a success payload."""
                del request
                return JsonResponse({"ok": True})

        view = DecoratedView.as_view()

        first_response = view(
            RequestFactory().get(
                "/decorated/",
                REMOTE_ADDR="203.0.113.12",
                HTTP_USER_AGENT="pytest-agent",
            )
        )
        second_request = RequestFactory().get(
            "/decorated/",
            REMOTE_ADDR="203.0.113.12",
            HTTP_USER_AGENT="pytest-agent",
        )
        second_response = view(second_request)

        assert first_response.status_code == 200
        assert second_response.status_code == 429
        assert isinstance(second_response, HttpResponse)
        payload = json.loads(second_response.content)
        assert "throttled" in payload["detail"].lower()
        assert "request_id" in payload

    def test_blocks_request_over_limit_logs_security_event(
        self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Throttle denials emit a structured security log with the request context."""
        monkeypatch.setattr(logging.getLogger("api"), "propagate", True)

        @throttle("1/minute")
        class DecoratedView(View):
            """Simple view used for throttle decorator tests."""

            def get(self, request: HttpRequest) -> JsonResponse:
                """Return a success payload."""
                del request
                return JsonResponse({"ok": True})

        view = DecoratedView.as_view()

        _ = view(
            RequestFactory().get(
                "/decorated/",
                REMOTE_ADDR="203.0.113.12",
                HTTP_USER_AGENT="pytest-agent",
            )
        )
        second_request = RequestFactory().get(
            "/decorated/",
            REMOTE_ADDR="203.0.113.12",
            HTTP_USER_AGENT="pytest-agent",
        )

        with caplog.at_level(logging.WARNING, logger="api.throttling"):
            response = view(second_request)

        assert response.status_code == 429
        record = cast(
            Any, next(r for r in caplog.records if r.name == "api.throttling")
        )
        assert record.event_type == "RATE_LIMIT_TRIGGERED"
        assert record.action_attempted == "GET"
        assert record.result == "failure"
        assert record.status_code == 429

    def test_includes_retry_after_header(self) -> None:
        """Throttle denial includes a numeric Retry-After header."""

        @throttle("1/minute")
        class DecoratedView(View):
            """Simple view used for throttle decorator tests."""

            def get(self, request: HttpRequest) -> JsonResponse:
                """Return a success payload."""
                del request
                return JsonResponse({"ok": True})

        view = DecoratedView.as_view()

        _ = view(RequestFactory().get("/decorated/"))
        response = view(RequestFactory().get("/decorated/"))

        assert response.status_code == 429
        assert "Retry-After" in response
        assert response["Retry-After"].isdigit()

    def test_preserves_view_class_attributes(self) -> None:
        """Applying throttle decorator does not remove auth policy metadata."""

        @throttle("10/minute")
        @authz_roles("app_admin")
        class DecoratedView(View):
            """Simple view used for throttle decorator tests."""

            marker: str = "kept"

            def get(self, request: HttpRequest) -> JsonResponse:
                """Return a success payload."""
                del request
                return JsonResponse({"ok": True})

        assert getattr(DecoratedView, "authz_policy") == "roles"
        assert getattr(DecoratedView, "authz_roles") == ("app_admin",)
        assert DecoratedView.marker == "kept"

    def test_sets_throttle_rate_attribute(self) -> None:
        """Decorator stores the rate on the class for introspection."""

        @throttle("42/hour")
        class DecoratedView(View):
            """Simple view used for throttle decorator tests."""

            def get(self, request: HttpRequest) -> JsonResponse:
                """Return a success payload."""
                del request
                return JsonResponse({"ok": True})

        assert getattr(DecoratedView, "_throttle_rate") == "42/hour"


class TestThrottleDecoratorOnFunction:
    """Tests for @throttle applied to function-based views."""

    @pytest.fixture(autouse=True)
    def clear_cache(self) -> None:
        """Clear cache to keep throttle state isolated across tests."""
        cache.clear()

    def test_allows_request_under_limit(self) -> None:
        """Request under configured limit reaches the wrapped function."""

        @throttle("10/minute")
        def my_view(request: HttpRequest) -> JsonResponse:
            """Return a success payload."""
            del request
            return JsonResponse({"ok": True})

        response = my_view(RequestFactory().get("/func/"))

        assert response.status_code == 200
        assert isinstance(response, HttpResponse)
        assert json.loads(response.content) == {"ok": True}

    def test_blocks_request_over_limit(self) -> None:
        """Second request in same window is blocked with 429 response."""

        @throttle("1/minute")
        def my_view(request: HttpRequest) -> JsonResponse:
            """Return a success payload."""
            del request
            return JsonResponse({"ok": True})

        first_response = my_view(RequestFactory().get("/func/"))
        second_response = my_view(RequestFactory().get("/func/"))

        assert first_response.status_code == 200
        assert second_response.status_code == 429
        assert isinstance(second_response, HttpResponse)
        payload = json.loads(second_response.content)
        assert "throttled" in payload["detail"].lower()
        assert "request_id" in payload

    def test_includes_retry_after_header(self) -> None:
        """Throttle denial includes a numeric Retry-After header."""

        @throttle("1/minute")
        def my_view(request: HttpRequest) -> JsonResponse:
            """Return a success payload."""
            del request
            return JsonResponse({"ok": True})

        _ = my_view(RequestFactory().get("/func/"))
        response = my_view(RequestFactory().get("/func/"))

        assert response.status_code == 429
        assert "Retry-After" in response
        assert response["Retry-After"].isdigit()

    def test_sets_throttle_rate_attribute(self) -> None:
        """Decorator stores the rate on the function for introspection."""

        @throttle("42/hour")
        def my_view(request: HttpRequest) -> JsonResponse:
            """Return a success payload."""
            del request
            return JsonResponse({"ok": True})

        assert getattr(my_view, "_throttle_rate") == "42/hour"

    def test_passes_through_when_no_request_in_args(self) -> None:
        """Callable without an HttpRequest arg skips throttle check."""

        @throttle("1/minute")
        def plain_func(value: int) -> int:
            """Return the value unchanged."""
            return value

        assert plain_func(42) == 42


class TestThrottleDecoratorEdgeCases:
    """Edge-case tests for the @throttle decorator."""

    def test_raises_type_error_for_non_view_non_callable(self) -> None:
        """Applying @throttle to an invalid target raises TypeError."""
        with pytest.raises(TypeError, match="@throttle can only decorate"):
            throttle("10/minute")("not_a_view_or_callable")


class TestThrottleExempt:
    """Tests for @throttle_exempt decorator."""

    @pytest.fixture(autouse=True)
    def clear_cache(self) -> None:
        """Clear cache to keep throttle state isolated across tests."""
        cache.clear()

    def test_sets_throttle_rate_none_on_class(self) -> None:
        """Decorator sets _throttle_rate=None on a class-based view."""

        @throttle_exempt
        class StubView(View):
            """View stub for throttle exempt test."""

            def get(self, request: HttpRequest) -> JsonResponse:
                """Return a success payload."""
                del request
                return JsonResponse({"ok": True})

        assert hasattr(StubView, THROTTLE_RATE_ATTR)
        assert getattr(StubView, THROTTLE_RATE_ATTR) is None

    def test_sets_throttle_rate_none_on_callable(self) -> None:
        """Decorator sets _throttle_rate=None on a function-based view."""

        @throttle_exempt
        def my_view(request: HttpRequest) -> JsonResponse:
            """Return a success payload."""
            del request
            return JsonResponse({"ok": True})

        assert hasattr(my_view, THROTTLE_RATE_ATTR)
        assert getattr(my_view, THROTTLE_RATE_ATTR) is None

    def test_exempt_view_allows_unlimited_requests(self) -> None:
        """Exempt view passes all requests without throttle check."""

        @throttle_exempt
        class StubView(View):
            """View stub for throttle exempt test."""

            def get(self, request: HttpRequest) -> JsonResponse:
                """Return a success payload."""
                del request
                return JsonResponse({"ok": True})

        view = StubView.as_view()
        for _ in range(5):
            response = view(RequestFactory().get("/exempt/"))
            assert response.status_code == 200


class TestThrottleHelpers:
    """Tests for helper utilities used by throttle decorator."""

    def test_throttle_wait_seconds_handles_none(self) -> None:
        """No wait duration returns None for Retry-After handling."""

        class _FakeThrottle:
            def wait(self) -> None:
                return None

        assert _throttle_wait_seconds(_FakeThrottle()) is None  # type: ignore[arg-type]  # lightweight stub replacing SimpleRateThrottle for unit test isolation

    def test_throttle_detail_without_wait_uses_default_message(self) -> None:
        """Detail builder falls back to DRF default message when wait missing."""
        detail = _throttle_detail(None)
        assert "throttled" in detail.lower()


class _AuthenticatedUser:
    """Test helper representing an authenticated request user."""

    is_authenticated = True

    def __init__(self, username: str) -> None:
        """Store the user identity used by throttle key generation."""
        self._username = username

    def get_username(self) -> str:
        """Return the configured username identity."""
        return self._username
