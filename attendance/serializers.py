from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import Attendance


class PositionSerializer(serializers.Serializer):
    latitude = serializers.FloatField(min_value=-90, max_value=90)
    longitude = serializers.FloatField(min_value=-180, max_value=180)


class AttendanceSerializer(serializers.ModelSerializer):
    """Pointage du jour. `status` : before_entry, in_progress ou done."""

    clock_in = serializers.SerializerMethodField()
    clock_out = serializers.SerializerMethodField()
    clock_in_time = serializers.SerializerMethodField()
    clock_out_time = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = Attendance
        fields = ["date", "clock_in", "clock_out", "clock_in_time", "clock_out_time", "status"]
        read_only_fields = fields

    def get_clock_in(self, obj) -> str:
        return timezone.localtime(obj.clock_in).isoformat()

    def get_clock_out(self, obj) -> str | None:
        return timezone.localtime(obj.clock_out).isoformat() if obj.clock_out else None

    def get_clock_in_time(self, obj) -> str:
        return timezone.localtime(obj.clock_in).strftime("%H:%M")

    def get_clock_out_time(self, obj) -> str | None:
        return timezone.localtime(obj.clock_out).strftime("%H:%M") if obj.clock_out else None

    def get_status(self, obj) -> str:
        return "done" if obj.clock_out else "in_progress"
