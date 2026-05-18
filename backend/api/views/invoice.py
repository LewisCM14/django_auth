"""Equipment serial list API endpoint backed by the Oracle service layer."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from rest_framework.response import Response

from api.adapters.oracle import OracleAdapter
from api.caching import cache_private
from api.constants import ROLE_ADMIN, ROLE_VIEWER
from api.permissions import authz_roles
from api.serializers import EquipmentSerialListResponseSerializer, EquipmentSerialQuerySerializer
from api.services.oracle_invoice_service import get_oracle_adapter, list_equipment_serial_numbers
from api.throttling import throttle
from api.views.base import BaseAPIView


@throttle("30/minute")
@cache_private
@authz_roles(ROLE_ADMIN, ROLE_VIEWER)
class InvoiceListView(BaseAPIView):
    serializer_class = EquipmentSerialListResponseSerializer
    oracle_adapter_provider: Callable[[], OracleAdapter] = staticmethod(get_oracle_adapter)

    def get(self, request: Any) -> Response:
        query_serializer = EquipmentSerialQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)

        rows = list_equipment_serial_numbers(
            name=query_serializer.validated_data["name"],
            request=request,
            adapter=self.oracle_adapter_provider(),
        )

        response_serializer = EquipmentSerialListResponseSerializer(
            {"count": len(rows), "results": rows}
        )
        return Response(response_serializer.data)
