"""Project-level URL routing.

Delegates all API routing to the api.urls module. This module only
handles project-level path inclusion and does not define views directly.
"""
from django.urls import URLPattern, URLResolver, include, path

from api.views.docs import SchemaView, SwaggerDocsView


urlpatterns: list[URLPattern | URLResolver] = [
    # OpenAPI schema
    path("api/schema/", SchemaView.as_view(), name="schema"),
    # Swagger UI documentation
    path(
        "api/docs/",
        SwaggerDocsView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    # API routes
    path("api/", include("api.urls")),
]
