from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsManager

from . import reports, services
from .models import LeaveRequest
from .serializers import (
    ApprovalSerializer,
    LeaveRequestCreateSerializer,
    LeaveRequestSerializer,
    RefuseSerializer,
)
from .simple_pdf import create_pdf

MONTH_PARAM = OpenApiParameter("month", str, description="Mois au format AAAA-MM (défaut : mois courant)")


class BalanceView(APIView):
    """Solde de congés payés de l'utilisateur connecté."""

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response(services.paid_balance(request.user, timezone.localdate()))


class MyRequestsView(generics.ListCreateAPIView):
    """Mes demandes (GET) et création d'une demande (POST)."""

    def get_queryset(self):
        return LeaveRequest.objects.filter(employee=self.request.user).select_related("employee", "decided_by")

    def get_serializer_class(self):
        return LeaveRequestCreateSerializer if self.request.method == "POST" else LeaveRequestSerializer

    @extend_schema(request=LeaveRequestCreateSerializer, responses={201: LeaveRequestSerializer})
    def create(self, request, *args, **kwargs):
        serializer = LeaveRequestCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            instance = serializer.save()
        return Response(LeaveRequestSerializer(instance).data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Espace manager (rôle « manager » obligatoire ; un manager ne voit que SON équipe)
# ---------------------------------------------------------------------------

class ApprovalsView(generics.ListAPIView):
    """Demandes en attente de décision pour l'équipe du manager."""

    permission_classes = [IsManager]
    serializer_class = ApprovalSerializer

    def get_queryset(self):
        return (
            LeaveRequest.objects.filter(
                employee__manager=self.request.user, status=LeaveRequest.Status.PENDING
            )
            .select_related("employee", "decided_by")
            .order_by("start_date")
        )


class TeamRequestsView(generics.ListAPIView):
    """Toutes les demandes de l'équipe du manager (tous statuts), pour l'export mensuel."""

    permission_classes = [IsManager]
    serializer_class = LeaveRequestSerializer

    def get_queryset(self):
        return (
            LeaveRequest.objects.filter(employee__manager=self.request.user)
            .select_related("employee", "decided_by")
            .order_by("start_date")
        )


def _conflict(message: str) -> Response:
    return Response({"detail": message}, status=status.HTTP_409_CONFLICT)


class ApproveView(APIView):
    """Approuve une demande : le solde est revérifié au moment de la décision."""

    permission_classes = [IsManager]

    @extend_schema(request=None, responses=ApprovalSerializer)
    def post(self, request, pk):
        with transaction.atomic():
            leave = get_object_or_404(
                LeaveRequest.objects.select_for_update().select_related("employee"),
                pk=pk, employee__manager=request.user,
            )
            if leave.status != LeaveRequest.Status.PENDING:
                return _conflict("Cette demande a déjà été traitée.")

            if leave.leave_type == LeaveRequest.LeaveType.PAID:
                remaining = services.paid_balance(leave.employee, leave.start_date)["remaining"]
                if leave.days > remaining:
                    return _conflict("Solde insuffisant : la demande ne peut plus être approuvée.")

            leave.status = LeaveRequest.Status.APPROVED
            leave.decided_by = request.user
            leave.decided_at = timezone.now()
            leave.save(update_fields=["status", "decided_by", "decided_at"])
        return Response(ApprovalSerializer(leave).data)


class RefuseView(APIView):
    """Refuse une demande. Le motif est obligatoire ; les jours ne sont pas déduits."""

    permission_classes = [IsManager]

    @extend_schema(request=RefuseSerializer, responses=ApprovalSerializer)
    def post(self, request, pk):
        serializer = RefuseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            leave = get_object_or_404(
                LeaveRequest.objects.select_for_update().select_related("employee"),
                pk=pk, employee__manager=request.user,
            )
            if leave.status != LeaveRequest.Status.PENDING:
                return _conflict("Cette demande a déjà été traitée.")
            leave.status = LeaveRequest.Status.REFUSED
            leave.refusal_reason = serializer.validated_data["reason"]
            leave.decided_by = request.user
            leave.decided_at = timezone.now()
            leave.save(update_fields=["status", "refusal_reason", "decided_by", "decided_at"])
        return Response(ApprovalSerializer(leave).data)


def _report_for(request):
    """Construit le rapport du mois demandé, ou None si le paramètre `month` est invalide."""
    try:
        month = reports.parse_month(request.query_params.get("month"))
    except ValueError:
        return None
    return reports.build_report(request.user, month)


class ReportView(APIView):
    """Aperçu JSON de l'export mensuel (congés de l'équipe + pointages)."""

    permission_classes = [IsManager]

    @extend_schema(parameters=[MONTH_PARAM], responses=OpenApiTypes.OBJECT)
    def get(self, request):
        report = _report_for(request)
        if report is None:
            return Response({"month": ["Format attendu : AAAA-MM."]}, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            "month": report.month.strftime("%Y-%m"),
            "title": report.title,
            "approved_days": report.approved_days,
            "pending_days": report.pending_days,
            "refused_count": report.refused_count,
            "leave_lines": [
                {
                    "employee": l.employee, "leave_type": l.leave_type,
                    "start_date": l.start, "end_date": l.end,
                    "working_days_in_month": l.working_days_in_month, "status": l.status,
                }
                for l in report.leave_lines
            ],
            "attendance_lines": [
                {
                    "employee": a.employee, "date": a.day, "clock_in": a.clock_in,
                    "clock_out": a.clock_out, "hours": a.hours,
                }
                for a in report.attendance_lines
            ],
        })


class ReportExportView(APIView):
    """Téléchargement de l'export mensuel : `?month=AAAA-MM&format=pdf|csv`."""

    permission_classes = [IsManager]

    @extend_schema(parameters=[MONTH_PARAM, OpenApiParameter("format", str, enum=["pdf", "csv"])],
                   responses=OpenApiTypes.BINARY)
    def get(self, request):
        report = _report_for(request)
        if report is None:
            return Response({"month": ["Format attendu : AAAA-MM."]}, status=status.HTTP_400_BAD_REQUEST)

        fmt = request.query_params.get("format", "pdf").lower()
        stem = f"Taskify_Export_{report.month:%Y-%m}"
        if fmt == "csv":
            response = HttpResponse(reports.to_csv(report), content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = f'attachment; filename="{stem}.csv"'
        elif fmt == "pdf":
            response = HttpResponse(create_pdf(reports.to_pdf_lines(report)), content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="{stem}.pdf"'
        else:
            return Response({"format": ["Valeurs possibles : pdf, csv."]}, status=status.HTTP_400_BAD_REQUEST)
        return response
