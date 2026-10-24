"""Export mensuel pour le manager : congés de son équipe + pointages (CSV ou PDF)."""
import calendar
from dataclasses import dataclass, field
from datetime import date, datetime

from django.utils import timezone

from attendance.models import Attendance

from .models import LeaveRequest
from .services import working_days

STATUS_FR = {
    LeaveRequest.Status.PENDING: "En attente",
    LeaveRequest.Status.APPROVED: "Approuvé",
    LeaveRequest.Status.REFUSED: "Refusé",
}
MONTHS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
             "août", "septembre", "octobre", "novembre", "décembre"]


@dataclass
class LeaveLine:
    employee: str
    leave_type: str
    start: date
    end: date
    working_days_in_month: int
    status: str  # "pending" | "approved" | "refused"


@dataclass
class AttendanceLine:
    employee: str
    day: date
    clock_in: str
    clock_out: str
    hours: float | None


@dataclass
class MonthlyReport:
    month: date  # 1er jour du mois
    manager: str
    team: str
    leave_lines: list[LeaveLine] = field(default_factory=list)
    attendance_lines: list[AttendanceLine] = field(default_factory=list)

    @property
    def title(self) -> str:
        return f"{MONTHS_FR[self.month.month - 1].capitalize()} {self.month.year}"

    @property
    def approved_days(self) -> int:
        return sum(l.working_days_in_month for l in self.leave_lines if l.status == "approved")

    @property
    def pending_days(self) -> int:
        return sum(l.working_days_in_month for l in self.leave_lines if l.status == "pending")

    @property
    def refused_count(self) -> int:
        return sum(1 for l in self.leave_lines if l.status == "refused")


def parse_month(value: str | None) -> date:
    """« 2026-10 » → 2026-10-01 ; sans valeur : mois courant. Lève ValueError si invalide."""
    if not value:
        today = timezone.localdate()
        return date(today.year, today.month, 1)
    parsed = datetime.strptime(value, "%Y-%m")
    return date(parsed.year, parsed.month, 1)


def build_report(manager, month: date) -> MonthlyReport:
    last = date(month.year, month.month, calendar.monthrange(month.year, month.month)[1])
    team = manager.reports.all()

    report = MonthlyReport(month=month, manager=manager.full_name, team=manager.team)

    requests = (
        LeaveRequest.objects.filter(employee__in=team, start_date__lte=last, end_date__gte=month)
        .select_related("employee")
        .order_by("employee__full_name", "start_date")
    )
    for r in requests:
        # seuls les jours ouvrés qui tombent dans ce mois sont comptés
        days = working_days(max(r.start_date, month), min(r.end_date, last))
        report.leave_lines.append(
            LeaveLine(r.employee.full_name, r.leave_type, r.start_date, r.end_date, days, r.status)
        )

    rows = (
        Attendance.objects.filter(employee__in=team, date__gte=month, date__lte=last)
        .select_related("employee")
        .order_by("employee__full_name", "date")
    )
    for a in rows:
        report.attendance_lines.append(
            AttendanceLine(
                a.employee.full_name, a.date,
                timezone.localtime(a.clock_in).strftime("%H:%M"),
                timezone.localtime(a.clock_out).strftime("%H:%M") if a.clock_out else "",
                a.worked_hours,
            )
        )
    return report


def _d(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def _hours(value: float | None) -> str:
    return "" if value is None else f"{value:.2f}".replace(".", ",")


def _csv_escape(value: str) -> str:
    if ";" in value or '"' in value or "\n" in value:
        return '"' + value.replace('"', '""') + '"'
    return value


def to_csv(report: MonthlyReport) -> bytes:
    """CSV séparé par « ; » (Excel en français), encodé UTF-8 avec BOM pour les accents."""
    rows = ["Congés", "Employé;Type;Début;Fin;Jours ouvrés dans le mois;Statut"]
    for l in report.leave_lines:
        rows.append(";".join([
            _csv_escape(l.employee), _csv_escape(l.leave_type), _d(l.start), _d(l.end),
            str(l.working_days_in_month), STATUS_FR[l.status],
        ]))
    rows += ["", "Pointages", "Employé;Date;Entrée;Sortie;Heures travaillées"]
    for a in report.attendance_lines:
        rows.append(";".join([_csv_escape(a.employee), _d(a.day), a.clock_in, a.clock_out, _hours(a.hours)]))
    return ("\ufeff" + "\r\n".join(rows) + "\r\n").encode("utf-8")


def to_pdf_lines(report: MonthlyReport) -> list[str]:
    lines = [
        "Taskify HR - Export mensuel",
        "",
        f"Mois : {report.title}",
        f"Équipe : {report.team} - Manager : {report.manager}",
        f"Généré le {timezone.localtime().strftime('%d/%m/%Y %H:%M')}",
        "",
        f"Demandes : {len(report.leave_lines)}   Jours approuvés : {report.approved_days}   "
        f"Jours en attente : {report.pending_days}   Refusées : {report.refused_count}",
        "",
        "CONGÉS",
        "Employé | Type | Période | Jours ouvrés | Statut",
        "-" * 60,
    ]
    for l in report.leave_lines:
        lines.append(
            f"{l.employee} | {l.leave_type} | {_d(l.start)} - {_d(l.end)} | "
            f"{l.working_days_in_month} j | {STATUS_FR[l.status]}"
        )
    lines += ["", "POINTAGES", "Employé | Date | Entrée | Sortie | Heures", "-" * 60]
    for a in report.attendance_lines:
        lines.append(f"{a.employee} | {_d(a.day)} | {a.clock_in} | {a.clock_out or '-'} | {_hours(a.hours) or '-'}")
    return lines
