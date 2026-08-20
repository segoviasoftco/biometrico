"""Serializers de autenticacion y gestion de usuarios del sistema."""

from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.accounts.models import Usuario


class LoginSerializer(TokenObtainPairSerializer):
    """Agrega los datos del usuario a la respuesta del login.

    Evita que el frontend tenga que hacer una segunda peticion solo para saber
    el rol y decidir que menu mostrar.
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["rol"] = user.rol
        token["nombre_completo"] = user.nombre_completo
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data["usuario"] = UsuarioSerializer(self.user).data
        return data


class UsuarioSerializer(serializers.ModelSerializer):
    """Lectura de los datos de un usuario del sistema."""

    nombre_completo = serializers.CharField(read_only=True)
    rol_display = serializers.CharField(source="get_rol_display", read_only=True)
    sede_nombre = serializers.CharField(source="sede.nombre", read_only=True, default=None)

    class Meta:
        model = Usuario
        fields = [
            "id",
            "email",
            "nombres",
            "apellidos",
            "nombre_completo",
            "rol",
            "rol_display",
            "telefono",
            "sede",
            "sede_nombre",
            "is_active",
            "last_login",
            "creado_en",
        ]
        read_only_fields = ["id", "last_login", "creado_en"]


class UsuarioEscrituraSerializer(serializers.ModelSerializer):
    """Alta y edicion de usuarios, con la clave gestionada aparte."""

    password = serializers.CharField(
        write_only=True, required=False, allow_blank=True, style={"input_type": "password"}
    )

    class Meta:
        model = Usuario
        fields = [
            "id",
            "email",
            "nombres",
            "apellidos",
            "rol",
            "telefono",
            "sede",
            "is_active",
            "password",
        ]

    def validate(self, attrs):
        # Un supervisor sin sede veria los datos de toda la organizacion, que es
        # justo lo que su rol debe evitar.
        rol = attrs.get("rol", getattr(self.instance, "rol", None))
        sede = attrs.get("sede", getattr(self.instance, "sede", None))
        if rol == Usuario.Rol.SUPERVISOR and sede is None:
            raise serializers.ValidationError(
                {"sede": "Un supervisor debe tener una sede asignada."}
            )
        return attrs

    def validate_password(self, value):
        if value:
            validate_password(value)
        return value

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        if not password:
            raise serializers.ValidationError(
                {"password": "La clave es obligatoria al crear un usuario."}
            )
        return Usuario.objects.create_user(password=password, **validated_data)

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        usuario = super().update(instance, validated_data)
        if password:
            usuario.set_password(password)
            usuario.save(update_fields=["password"])
        return usuario


class CambiarPasswordSerializer(serializers.Serializer):
    """Cambio de clave por parte del propio usuario."""

    password_actual = serializers.CharField(style={"input_type": "password"})
    password_nueva = serializers.CharField(style={"input_type": "password"})

    def validate_password_actual(self, value):
        usuario = self.context["request"].user
        if not usuario.check_password(value):
            raise serializers.ValidationError("La clave actual no es correcta.")
        return value

    def validate_password_nueva(self, value):
        validate_password(value, self.context["request"].user)
        return value

    def save(self, **kwargs):
        usuario = self.context["request"].user
        usuario.set_password(self.validated_data["password_nueva"])
        usuario.save(update_fields=["password"])
        return usuario
