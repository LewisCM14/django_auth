"""API endpoint routing.

Defines URL patterns for all API endpoints. This module is included at the
project level via config/urls.py.
"""

from __future__ import annotations

from django.urls import URLPattern, path

from api.views.health import HealthView
from api.views.invoice import InvoiceListView
from api.views.user import UserView


urlpatterns: list[URLPattern] = [
    path("health/", HealthView.as_view(), name="health"),
    path(
        "equipment/<str:equipment_name>/serial_numbers/",
        InvoiceListView.as_view(),
        name="equipment-serial-number-list",
    ),
    # Backward-compatible alias retained for existing clients/tests migrating
    # from the previous invoice example route.
    path(
        "invoices/",
        InvoiceListView.as_view(),
        {"equipment_name": ""},
        name="invoice-list-legacy",
    ),
    path("user/", UserView.as_view(), name="user"),
]
