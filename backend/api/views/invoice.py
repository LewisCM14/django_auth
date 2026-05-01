"""Invoice list API endpoint backed by the Oracle service layer.

This module keeps view logic transport-focused:
- Parse and validate query parameters.
- Delegate data access to the service layer.
- Serialize a stable response envelope.

Cross-cutting concerns such as authorization, throttling, cache headers, and
exception shaping are applied by decorators and middleware.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from rest_framework.response import Response

from api.adapters.oracle import OracleAdapter
from api.caching import cache_private
from api.constants import ROLE_ADMIN, ROLE_VIEWER
from api.permissions import authz_roles
from api.serializers import InvoiceListQuerySerializer, InvoiceListResponseSerializer
from api.services.oracle_invoice_service import get_oracle_adapter, list_invoices
from api.throttling import throttle
from api.views.base import BaseAPIView


@throttle("30/minute")
@cache_private
@authz_roles(ROLE_ADMIN, ROLE_VIEWER)
class InvoiceListView(BaseAPIView):
    """Read-only invoices endpoint for admin and viewer roles.

    Decorator order is intentionally throttle -> cache -> authorization to align
    with project guardrails and keep policy behavior predictable.
    """

    serializer_class = InvoiceListResponseSerializer
    oracle_adapter_provider: Callable[[], OracleAdapter] = staticmethod(
        get_oracle_adapter
    )

    def get(self, request: Any) -> Response:
        """Return invoices filtered by optional status and bounded row limit.

        Args:
            request: DRF request carrying query parameters and request context.

        Returns:
            DRF response with count and normalized invoice row results.

        Raises:
            ValidationError: If query parameter validation fails.
        """

        query_serializer = InvoiceListQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)

        # Service handles Oracle query execution and structured success logging.
        rows = list_invoices(
            status=query_serializer.validated_data.get("status"),
            limit=query_serializer.validated_data["limit"],
            request=request,
            adapter=self.oracle_adapter_provider(),
        )

        response_payload = {
            "count": len(rows),
            "results": rows,
        }
        # Serialize output explicitly so schema and response shape stay aligned.
        response_serializer = InvoiceListResponseSerializer(response_payload)
        return Response(response_serializer.data)
