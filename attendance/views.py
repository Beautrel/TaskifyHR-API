from django.db import IntegrityError, transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .models import Attendance
from .serializers import AttendanceSerializer, PositionSerializer

BEFORE_ENTRY = {"date": None, "clock_in": None, "clock_out": None,
                "clock_in_time": None, "clock_out_time": None, "status": "before_entry"}


def _error(code: str, message: str, http_status: int) -> Response:
    return Response({"code": code, "detail": message}, status=http_status)


def _check_position(request):
    """Valide la position envoyée et vérifie qu'elle est dans la zone. Retourne (position, erreur)."""
    serializer = PositionSerializer(data=request.data)
    if not serializer.is_valid():
        return None, _error("position_required", "La position est requise pour pointer.",
                            status.HTTP_400_BAD_REQUEST)
    position = serializer.validated_data
    if not services.is_in_zone(position["latitude"], position["longitude"]):
        return None, _error("out_of_zone", "Vous êtes en dehors de la zone de pointage.",
                            status.HTTP_403_FORBIDDEN)
    return position, None


class TodayView(APIView):
    """Pointage du jour de l'utilisateur connecté."""

    @extend_schema(responses=AttendanceSerializer)
    def get(self, request):
        today = timezone.localdate()
        attendance = Attendance.objects.filter(employee=request.user, date=today).first()
        if attendance is None:
            return Response({**BEFORE_ENTRY, "date": today})
        return Response(AttendanceSerializer(attendance).data)


class ClockInView(APIView):
    """Pointe l'entrée (heure du serveur). Une seule entrée par jour."""

    @extend_schema(request=PositionSerializer, responses={201: AttendanceSerializer})
    def post(self, request):
        position, error = _check_position(request)
        if error:
            return error

        today = timezone.localdate()
        try:
            with transaction.atomic():
                attendance = Attendance.objects.create(
                    employee=request.user, date=today, clock_in=timezone.now(),
                    in_latitude=position["latitude"], in_longitude=position["longitude"],
                )
        except IntegrityError:
            return _error("already_clocked_in", "Entrée déjà enregistrée aujourd'hui.",
                          status.HTTP_409_CONFLICT)
        return Response(AttendanceSerializer(attendance).data, status=status.HTTP_201_CREATED)


class ClockOutView(APIView):
    """Pointe la sortie (heure du serveur). Une seule sortie par jour, après l'entrée."""

    @extend_schema(request=PositionSerializer, responses=AttendanceSerializer)
    def post(self, request):
        position, error = _check_position(request)
        if error:
            return error

        with transaction.atomic():
            attendance = (
                Attendance.objects.select_for_update()
                .filter(employee=request.user, date=timezone.localdate()).first()
            )
            if attendance is None:
                return _error("no_clock_in", "Aucune entrée enregistrée aujourd'hui.",
                              status.HTTP_409_CONFLICT)
            if attendance.clock_out is not None:
                return _error("already_clocked_out", "Sortie déjà enregistrée aujourd'hui.",
                              status.HTTP_409_CONFLICT)
            attendance.clock_out = timezone.now()
            attendance.out_latitude = position["latitude"]
            attendance.out_longitude = position["longitude"]
            attendance.save(update_fields=["clock_out", "out_latitude", "out_longitude"])
        return Response(AttendanceSerializer(attendance).data)
