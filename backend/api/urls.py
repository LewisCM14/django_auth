"""API endpoint routing.

Defines URL patterns for all API endpoints. This module is included at the
project level via config/urls.py.
"""
from __future__ import annotations

from django.urls import URLPattern, path

from api.views.health import HealthView


urlpatterns: list[URLPattern] = [
    path("health/", HealthView.as_view(), name="health"),
]
