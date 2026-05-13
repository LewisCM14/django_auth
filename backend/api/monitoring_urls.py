"""Dedicated monitoring routes.

These routes are intentionally split from the main API URL tree so that IIS
can apply folder/path-level anonymous authentication settings specifically for
monitoring probes.
"""

from __future__ import annotations

from django.urls import URLPattern, path

from api.views.health import HealthView


urlpatterns: list[URLPattern] = [
    path("health/", HealthView.as_view(), name="monitoring-health"),
]
