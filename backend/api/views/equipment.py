"""Equipment serial hierarchy API endpoint backed by the Oracle service layer."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from api.adapters.oracle import OracleAdapter
from api.caching import cache_private
from api.constants import ROLE_ADMIN, ROLE_VIEWER
from api.permissions import authz_roles
from api.serializers import EquipmentSerialHierarchyResponseSerializer
from api.services.oracle_equipment_service import (
    get_equipment_serial_hierarchy,
    get_oracle_adapter,
)
from api.throttling import throttle
from api.views.base import BaseAPIView


@throttle("30/minute")
@cache_private
@authz_roles(ROLE_ADMIN, ROLE_VIEWER)
class EquipmentListView(BaseAPIView):
    serializer_class = EquipmentSerialHierarchyResponseSerializer
    oracle_adapter_provider: Callable[[], OracleAdapter] = staticmethod(
        get_oracle_adapter
    )

    def get(self, request: Any, equipment_name: str) -> Response:
        name = equipment_name.strip()
        if not name:
            raise ValidationError(
                {"equipment_name": ["This path parameter may not be blank."]}
            )

        result = get_equipment_serial_hierarchy(
            name=name,
            request=request,
            adapter=self.oracle_adapter_provider(),
        )

        response_serializer = EquipmentSerialHierarchyResponseSerializer(result)
        return Response(response_serializer.data)
