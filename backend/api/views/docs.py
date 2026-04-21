"""Schema and docs wrapper views with explicit authorization policy."""

from __future__ import annotations

import types
import typing

import drf_spectacular.openapi as spectacular_openapi
import drf_spectacular.plumbing as spectacular_plumbing
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from api.caching import cache_private
from api.permissions import authz_authenticated
from api.throttling import throttle
from api.views.base import BaseAPIView


def _is_higher_order_type_hint_compat(hint: object) -> bool:
    """Python 3.14-compatible replacement for drf-spectacular helper.

    drf-spectacular 0.29 inspects ``typing._UnionGenericAlias``, which emits a
    deprecation warning on Python 3.14+. This compatibility function keeps the
    same behavior needed by our schema generation path without touching the
    deprecated private typing alias.
    """

    return isinstance(
        hint,
        (
            getattr(types, "GenericAlias", tuple),
            getattr(types, "UnionType", tuple),
            getattr(typing, "_GenericAlias", tuple),
        ),
    )


spectacular_plumbing.is_higher_order_type_hint = _is_higher_order_type_hint_compat
spectacular_openapi.is_higher_order_type_hint = _is_higher_order_type_hint_compat


@throttle("10/minute")
@cache_private
@authz_authenticated
class SchemaView(SpectacularAPIView, BaseAPIView):
    """OpenAPI schema endpoint wrapper.

    Requires IIS authentication (any domain user) but no specific role.
    """


@throttle("30/minute")
@cache_private
@authz_authenticated
class SwaggerDocsView(SpectacularSwaggerView, BaseAPIView):
    """Swagger UI docs endpoint wrapper.

    Requires IIS authentication (any domain user) but no specific role.
    """
