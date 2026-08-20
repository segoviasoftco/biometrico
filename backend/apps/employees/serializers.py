"""Serializers del maestro de empleados."""

from rest_framework import serializers

from apps.employees.models import Empleado, HuellaEmpleado


class HuellaEmpleadoSerializer(serializers.ModelSerializer):
    """Metadatos de una huella respaldada.

    La plantilla en si no se expone por la API: es un dato biometrico y el
    frontend no tiene ningun uso para el.
    """

    class Meta:
        model = HuellaEmpleado
        fields = ["id", "finger_id", "size", "valid", "dispositivo_origen", "capturado_en"]
        read_only_fields = fields


class EmpleadoListaSerializer(serializers.ModelSerializer):
    """Version compacta para las tablas del frontend."""

    nombre_completo = serializers.CharField(read_only=True)
    sede_nombre = serializers.CharField(source="sede.nombre", read_only=True)
    departamento_nombre = serializers.CharField(source="departamento.nombre", read_only=True)
    cargo_nombre = serializers.CharField(source="cargo.nombre", read_only=True)
    estado_display = serializers.CharField(source="get_estado_display", read_only=True)

    class Meta:
        model = Empleado
        fields = [
            "id",
            "codigo_empleado",
            "dni",
            "nombre_completo",
            "foto",
            "sede",
            "sede_nombre",
            "departamento",
            "departamento_nombre",
            "cargo",
            "cargo_nombre",
            "estado",
            "estado_display",
            "tiene_huella",
            "tiene_rostro",
            "cantidad_huellas",
            "sincronizado_dispositivo",
        ]


class EmpleadoSerializer(serializers.ModelSerializer):
    """Ficha completa del empleado."""

    nombre_completo = serializers.CharField(read_only=True)
    sede_nombre = serializers.CharField(source="sede.nombre", read_only=True)
    departamento_nombre = serializers.CharField(source="departamento.nombre", read_only=True)
    area_nombre = serializers.CharField(source="area.nombre", read_only=True, default=None)
    cargo_nombre = serializers.CharField(source="cargo.nombre", read_only=True)
    estado_display = serializers.CharField(source="get_estado_display", read_only=True)
    tipo_contrato_display = serializers.CharField(
        source="get_tipo_contrato_display", read_only=True
    )
    huellas = HuellaEmpleadoSerializer(many=True, read_only=True)
    turno_actual = serializers.SerializerMethodField()

    class Meta:
        model = Empleado
        fields = [
            "id",
            "codigo_empleado",
            "dni",
            "nombres",
            "apellido_paterno",
            "apellido_materno",
            "nombre_completo",
            "fecha_nacimiento",
            "sexo",
            "foto",
            "email",
            "telefono",
            "direccion",
            "sede",
            "sede_nombre",
            "departamento",
            "departamento_nombre",
            "area",
            "area_nombre",
            "cargo",
            "cargo_nombre",
            "fecha_ingreso",
            "fecha_cese",
            "tipo_contrato",
            "tipo_contrato_display",
            "estado",
            "estado_display",
            "sueldo_basico",
            "tiene_huella",
            "cantidad_huellas",
            "tiene_rostro",
            "tiene_tarjeta",
            "numero_tarjeta",
            "privilegio_dispositivo",
            "password_dispositivo",
            "uid_dispositivo",
            "sincronizado_dispositivo",
            "fecha_ultima_sincronizacion",
            "huellas",
            "turno_actual",
            "creado_en",
            "actualizado_en",
        ]
        read_only_fields = [
            "id",
            # Los indicadores biometricos los define el dispositivo al
            # sincronizar, no se editan a mano desde la web.
            "tiene_huella",
            "cantidad_huellas",
            "tiene_rostro",
            "uid_dispositivo",
            "sincronizado_dispositivo",
            "fecha_ultima_sincronizacion",
            "creado_en",
            "actualizado_en",
        ]
        extra_kwargs = {"password_dispositivo": {"write_only": True}}

    def get_turno_actual(self, obj):
        from django.utils import timezone

        hoy = timezone.localdate()
        asignacion = (
            obj.asignaciones_turno.filter(fecha_inicio__lte=hoy)
            .filter(fecha_fin__isnull=True)
            .select_related("turno")
            .first()
        )
        if asignacion is None:
            return None
        return {"id": asignacion.turno.id, "nombre": asignacion.turno.nombre}

    def validate(self, attrs):
        # Un area de otro departamento produciria reportes cruzados, con el
        # empleado contado en dos partes distintas de la organizacion.
        departamento = attrs.get("departamento") or getattr(self.instance, "departamento", None)
        area = attrs.get("area") or getattr(self.instance, "area", None)
        if area and departamento and area.departamento_id != departamento.id:
            raise serializers.ValidationError(
                {"area": "El area seleccionada no pertenece al departamento indicado."}
            )

        if departamento:
            sede = attrs.get("sede") or getattr(self.instance, "sede", None)
            if sede and departamento.sede_id != sede.id:
                raise serializers.ValidationError(
                    {"departamento": "El departamento no pertenece a la sede indicada."}
                )

        fecha_ingreso = attrs.get("fecha_ingreso") or getattr(
            self.instance, "fecha_ingreso", None
        )
        fecha_cese = attrs.get("fecha_cese") or getattr(self.instance, "fecha_cese", None)
        if fecha_ingreso and fecha_cese and fecha_cese < fecha_ingreso:
            raise serializers.ValidationError(
                {"fecha_cese": "La fecha de cese no puede ser anterior a la de ingreso."}
            )

        return attrs
