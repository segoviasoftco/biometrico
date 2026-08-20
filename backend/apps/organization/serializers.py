"""Serializers de la estructura organizacional."""

from rest_framework import serializers

from apps.organization.models import Area, Cargo, Departamento, Sede


class SedeSerializer(serializers.ModelSerializer):
    total_empleados = serializers.IntegerField(read_only=True)

    class Meta:
        model = Sede
        fields = [
            "id",
            "nombre",
            "codigo",
            "direccion",
            "telefono",
            "activo",
            "total_empleados",
            "creado_en",
        ]
        read_only_fields = ["id", "creado_en"]


class DepartamentoSerializer(serializers.ModelSerializer):
    sede_nombre = serializers.CharField(source="sede.nombre", read_only=True)
    total_empleados = serializers.IntegerField(read_only=True)

    class Meta:
        model = Departamento
        fields = [
            "id",
            "nombre",
            "codigo",
            "sede",
            "sede_nombre",
            "descripcion",
            "activo",
            "total_empleados",
            "creado_en",
        ]
        read_only_fields = ["id", "creado_en"]


class AreaSerializer(serializers.ModelSerializer):
    departamento_nombre = serializers.CharField(source="departamento.nombre", read_only=True)
    sede_nombre = serializers.CharField(source="departamento.sede.nombre", read_only=True)

    class Meta:
        model = Area
        fields = [
            "id",
            "nombre",
            "codigo",
            "departamento",
            "departamento_nombre",
            "sede_nombre",
            "activo",
            "creado_en",
        ]
        read_only_fields = ["id", "creado_en"]


class CargoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cargo
        fields = ["id", "nombre", "descripcion", "activo", "creado_en"]
        read_only_fields = ["id", "creado_en"]
