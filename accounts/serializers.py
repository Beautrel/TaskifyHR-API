import re

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()

EMPLOYEE_ID_RE = re.compile(r"^[A-Za-z]{1,4}-\d{2,6}$")
PHONE_RE = re.compile(r"^\+?\d{8,15}$")


def normalize_phone(value: str) -> str:
    return "".join(c for c in value if c.isdigit() or c == "+")


class UserSerializer(serializers.ModelSerializer):
    """Profil de l'utilisateur (lecture)."""

    first_name = serializers.CharField(read_only=True)
    manager_name = serializers.SerializerMethodField()
    is_manager = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "full_name", "first_name", "email", "employee_id", "phone", "team",
            "job_title", "contract", "weekly_hours", "arrival_date",
            "manager_name", "role", "is_manager",
        ]
        read_only_fields = fields

    def get_manager_name(self, obj) -> str:
        return obj.manager.full_name if obj.manager else ""


class ProfileUpdateSerializer(serializers.ModelSerializer):
    """Seul le téléphone est modifiable ; le reste (RH, e-mail) est en lecture seule."""

    class Meta:
        model = User
        fields = ["phone"]

    def validate_phone(self, value):
        digits = normalize_phone(value)
        if not PHONE_RE.match(digits):
            raise serializers.ValidationError("Saisissez un numéro de téléphone valide.")
        return value.strip()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    class Meta:
        model = User
        fields = ["full_name", "email", "employee_id", "password"]

    def validate_full_name(self, value):
        value = value.strip()
        if len(value.split()) < 2:
            raise serializers.ValidationError("Saisissez votre prénom et votre nom.")
        return value

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Un compte existe déjà avec cette adresse e-mail.")
        return value

    def validate_employee_id(self, value):
        value = value.strip().upper()
        if not EMPLOYEE_ID_RE.match(value):
            raise serializers.ValidationError("Format attendu : TF-042.")
        if User.objects.filter(employee_id__iexact=value).exists():
            raise serializers.ValidationError("Ce matricule est déjà utilisé.")
        return value

    def validate_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value

    def create(self, validated_data):
        # Le nouvel employé est rattaché au premier manager existant (affectation par défaut).
        manager = User.objects.filter(role=User.Role.MANAGER).order_by("id").first()
        extra = {"manager": manager}
        if manager:
            extra["team"] = manager.team
        return User.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
            full_name=validated_data["full_name"],
            employee_id=validated_data["employee_id"],
            **extra,
        )


class LoginSerializer(TokenObtainPairSerializer):
    """Connexion par e-mail. Retourne les jetons JWT et le profil."""

    def validate(self, attrs):
        try:
            data = super().validate(attrs)
        except AuthenticationFailed:
            raise AuthenticationFailed(
                "Adresse e-mail ou mot de passe incorrect.", code="invalid_credentials"
            )
        data["user"] = UserSerializer(self.user).data
        return data
