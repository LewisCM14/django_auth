"""Helpers for resolving the user attached to a request."""

from __future__ import annotations

from typing import Any


def get_request_user(request: Any) -> Any:
    """Return the user attached by middleware, preserving authenticated state.

    DRF wraps ``HttpRequest`` objects and may replace ``request.user`` with
    its own anonymous placeholder when no DRF authentication class runs.
    The authentication middleware keeps the resolved identity on
    ``_cached_user`` so APIView-based endpoints can still access the same
    user object after DRF wraps the request.
    """

    underlying_request = getattr(request, "_request", request)
    cached_user = getattr(underlying_request, "_cached_user", None)
    if cached_user is not None:
        return cached_user
    return getattr(underlying_request, "user", None)
