from rest_framework import serializers

from . import services
from .models import LeaveRequest


class LeaveRequestSerializer(serializers.ModelSerializer):
    """Une demande de congé (lecture)."""

    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    team = serializers.CharField(source="employee.team", read_only=True)
    decided_by_name = serializers.SerializerMethodField()

    class Meta:
        model = LeaveRequest
        fields = [
            "id", "employee_name", "team", "leave_type", "start_date", "end_date", "days",
            "reason", "status", "decided_by_name", "refusal_reason", "created_at",
        ]
        read_only_fields = fields

    def get_decided_by_name(self, obj) -> str:
        return obj.decided_by.full_name if obj.decided_by else ""


class LeaveRequestCreateSerializer(serializers.ModelSerializer):
    """Création d'une demande : le serveur calcule les jours et applique les règles."""

    class Meta:
        model = LeaveRequest
        fields = ["leave_type", "start_date", "end_date", "reason"]
        extra_kwargs = {"reason": {"required": False}}

    def validate(self, attrs):
        user = self.context["request"].user
        attrs["days"] = services.validate_new_request(
            user, attrs["start_date"], attrs["end_date"],
            attrs.get("leave_type", LeaveRequest.LeaveType.PAID),
        )
        return attrs

    def create(self, validated_data):
        return LeaveRequest.objects.create(employee=self.context["request"].user, **validated_data)


class ApprovalSerializer(LeaveRequestSerializer):
    """Demande vue par le manager, avec le solde actuel de l'employé."""

    employee_remaining = serializers.SerializerMethodField()

    class Meta(LeaveRequestSerializer.Meta):
        fields = LeaveRequestSerializer.Meta.fields + ["employee_remaining"]
        read_only_fields = fields

    def get_employee_remaining(self, obj) -> int:
        return services.paid_balance(obj.employee, obj.start_date)["remaining"]


class RefuseSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=300, allow_blank=True, required=False, default="")

    def validate_reason(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Le motif du refus est obligatoire.")
        return value
