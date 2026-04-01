"""Schema and docs wrapper views with explicit authorization policy."""
from __future__ import annotations

from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from api.decorators import authz_public


@authz_public
class SchemaView(SpectacularAPIView):
    """OpenAPI schema endpoint wrapper.

    This wraps drf-spectacular's schema view so it lives under ``api.views``
    and can participate in strict per-view authorization policy enforcement.
    """


@authz_public
class SwaggerDocsView(SpectacularSwaggerView):
    """Swagger UI docs endpoint wrapper.

    This wraps drf-spectacular's swagger UI view so it lives under
    ``api.views`` and can participate in strict policy enforcement.
    """
