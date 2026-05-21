"""Serializer contracts for the Oracle-backed equipment serial endpoint."""

from __future__ import annotations

from rest_framework import serializers


class SerialDetailSerializer(serializers.Serializer):
    serial_number = serializers.CharField()
    type = serializers.CharField()
    description = serializers.CharField()


class EquipmentSubsystemSerializer(serializers.Serializer):
    subsystem = serializers.CharField(source="sub-system")
    serials = SerialDetailSerializer(many=True)


class EquipmentSerialHierarchyResponseSerializer(serializers.Serializer):
    equipment_id = serializers.CharField()
    equipment = serializers.CharField()
    system = serializers.CharField()
    subsystems = EquipmentSubsystemSerializer(many=True, source="sub-systems")
