"""Tests for HTTP cache-control decorators in api.caching."""

from __future__ import annotations

import pytest
from django.http import HttpRequest, JsonResponse
from django.test import RequestFactory
from django.views import View
from rest_framework.response import Response
from rest_framework.views import APIView

from api.caching import (
    CACHE_POLICY_ATTR,
    cache_disabled,
    cache_private,
    cache_public,
)


class TestCachePublicDecorator:
    """Tests for @cache_public(max_age=N) decorator."""

    def test_sets_policy_on_drf_view(self) -> None:
        """Decorator sets _cache_policy='public' on DRF APIView."""

        @cache_public(max_age=5)
        class StubView(APIView):
            """DRF view stub."""

        assert getattr(StubView, CACHE_POLICY_ATTR) == "public"

    def test_sets_policy_on_django_view(self) -> None:
        """Decorator sets _cache_policy='public' on Django View."""

        @cache_public(max_age=10)
        class StubView(View):
            """Django view stub."""

            def get(self, request: HttpRequest) -> JsonResponse:
                """Return a success payload."""
                del request
                return JsonResponse({"ok": True})

        assert getattr(StubView, CACHE_POLICY_ATTR) == "public"

    def test_applies_headers_to_drf_response(self) -> None:
        """DRF APIView response includes Cache-Control: public, max-age=5."""

        @cache_public(max_age=5)
        class StubView(APIView):
            """DRF view stub."""

            def get(self, request: HttpRequest) -> Response:
                """Return a success payload."""
                del request
                return Response({"status": "ok"})

        request = RequestFactory().get("/stub/")
        response = StubView.as_view()(request)
        response.render()
        assert "public" in response["Cache-Control"]
        assert "max-age=5" in response["Cache-Control"]

    def test_applies_headers_to_django_response(self) -> None:
        """Django View response includes Cache-Control: public, max-age=10."""

        @cache_public(max_age=10)
        class StubView(View):
            """Django view stub."""

            def get(self, request: HttpRequest) -> JsonResponse:
                """Return a success payload."""
                del request
                return JsonResponse({"ok": True})

        response = StubView.as_view()(RequestFactory().get("/stub/"))
        assert "public" in response["Cache-Control"]
        assert "max-age=10" in response["Cache-Control"]

    def test_sets_policy_on_callable(self) -> None:
        """Decorator sets _cache_policy='public' on a function-based view."""

        @cache_public(max_age=15)
        def my_view(request: HttpRequest) -> JsonResponse:
            """Return a success payload."""
            del request
            return JsonResponse({"ok": True})

        assert getattr(my_view, CACHE_POLICY_ATTR) == "public"
        response = my_view(RequestFactory().get("/"))
        assert "public" in response["Cache-Control"]

    def test_raises_for_invalid_target(self) -> None:
        """Applying @cache_public to a non-view raises TypeError."""
        with pytest.raises(TypeError, match="@cache_public"):
            cache_public(max_age=5)("not_a_view")  # type: ignore[arg-type]  # intentionally passing invalid type to test TypeError guard


class TestCachePrivateDecorator:
    """Tests for @cache_private decorator."""

    def test_sets_policy_on_drf_view(self) -> None:
        """Decorator sets _cache_policy='private' on DRF APIView."""

        @cache_private
        class StubView(APIView):
            """DRF view stub."""

        assert getattr(StubView, CACHE_POLICY_ATTR) == "private"

    def test_applies_headers_to_django_response(self) -> None:
        """Django View response includes Cache-Control: private, no-cache."""

        @cache_private
        class StubView(View):
            """Django view stub."""

            def get(self, request: HttpRequest) -> JsonResponse:
                """Return a success payload."""
                del request
                return JsonResponse({"ok": True})

        response = StubView.as_view()(RequestFactory().get("/stub/"))
        cc = response["Cache-Control"]
        assert "private" in cc
        assert "no-cache" in cc

    def test_sets_policy_on_callable(self) -> None:
        """Decorator sets _cache_policy='private' on a function-based view."""

        @cache_private
        def my_view(request: HttpRequest) -> JsonResponse:
            """Return a success payload."""
            del request
            return JsonResponse({"ok": True})

        assert getattr(my_view, CACHE_POLICY_ATTR) == "private"
        response = my_view(RequestFactory().get("/"))
        assert "private" in response["Cache-Control"]

    def test_raises_for_invalid_target(self) -> None:
        """Applying @cache_private to a non-view raises TypeError."""
        with pytest.raises(TypeError, match="@cache_private"):
            cache_private("not_a_view")  # type: ignore[arg-type]  # intentionally passing invalid type to test TypeError guard


class TestCacheDisabledDecorator:
    """Tests for @cache_disabled decorator."""

    def test_sets_policy_on_drf_view(self) -> None:
        """Decorator sets _cache_policy='disabled' on DRF APIView."""

        @cache_disabled
        class StubView(APIView):
            """DRF view stub."""

        assert getattr(StubView, CACHE_POLICY_ATTR) == "disabled"

    def test_applies_headers_to_django_response(self) -> None:
        """Django View response includes Cache-Control: no-store."""

        @cache_disabled
        class StubView(View):
            """Django view stub."""

            def get(self, request: HttpRequest) -> JsonResponse:
                """Return a success payload."""
                del request
                return JsonResponse({"ok": True})

        response = StubView.as_view()(RequestFactory().get("/stub/"))
        assert "no-store" in response["Cache-Control"]

    def test_sets_policy_on_callable(self) -> None:
        """Decorator sets _cache_policy='disabled' on a function-based view."""

        @cache_disabled
        def my_view(request: HttpRequest) -> JsonResponse:
            """Return a success payload."""
            del request
            return JsonResponse({"ok": True})

        assert getattr(my_view, CACHE_POLICY_ATTR) == "disabled"
        response = my_view(RequestFactory().get("/"))
        assert "no-store" in response["Cache-Control"]

    def test_raises_for_invalid_target(self) -> None:
        """Applying @cache_disabled to a non-view raises TypeError."""
        with pytest.raises(TypeError, match="@cache_disabled"):
            cache_disabled("not_a_view")  # type: ignore[arg-type]  # intentionally passing invalid type to test TypeError guard


class TestCacheCallableNonResponse:
    """Edge case: callable returning a non-HttpResponseBase value."""

    def test_non_response_passes_through_unchanged(self) -> None:
        """Wrapped callable returning non-response skips header patching."""

        @cache_private
        def plain_func(value: int) -> int:
            """Return the value unchanged."""
            return value

        assert plain_func(42) == 42
