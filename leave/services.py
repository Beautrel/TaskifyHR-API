"""Règles métier des congés. Tout ce qui doit TOUJOURS s'appliquer est ici,
indépendamment de ce que fait l'application mobile."""
from datetime import date, timedelta

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import LeaveRequest


def working_days(start: date, end: date) -> int:
    """Nombre de jours ouvrés (lundi à vendredi) entre deux dates, bornes incluses."""
    if end < start:
        return 0
    total = (end - start).days + 1
    return sum(1 for i in range(total) if (start + timedelta(days=i)).weekday() < 5)


def leave_period(ref: date) -> tuple[date, date, str]:
    """Période de congés : du 1er juin au 31 mai."""
    first_year = ref.year if ref.month >= 6 else ref.year - 1
    return (
        date(first_year, 6, 1),
        date(first_year + 1, 5, 31),
        f"juin {first_year} – mai {first_year + 1}",
    )


def paid_balance(user, ref: date) -> dict:
    """Solde de congés payés de `user` pour la période qui contient `ref`.

    - utilisés : demandes approuvées (les jours sont déduits uniquement à l'approbation)
    - en attente : demandes à valider (pas encore déduites)
    """
    start, end, label = leave_period(ref)
    paid = LeaveRequest.objects.filter(
        employee=user,
        leave_type=LeaveRequest.LeaveType.PAID,
        start_date__gte=start,
        start_date__lte=end,
    )

    def total(status):
        return paid.filter(status=status).aggregate(s=Sum("days"))["s"] or 0

    acquired = user.annual_leave_days or settings.TASKIFY["ANNUAL_LEAVE_DAYS"]
    used = total(LeaveRequest.Status.APPROVED)
    pending = total(LeaveRequest.Status.PENDING)
    return {
        "acquired": acquired,
        "used": used,
        "pending": pending,
        "remaining": acquired - used,
        "period": label,
    }


def validate_new_request(user, start: date, end: date, leave_type: str) -> int:
    """Applique toutes les règles de création d'une demande et retourne le nombre de jours ouvrés."""
    errors = {}
    today = timezone.localdate()

    if start <= today:
        errors["start_date"] = ["La date de début doit être future."]
    if end < start:
        errors["end_date"] = ["La fin doit être après le début."]
    if errors:
        raise ValidationError(errors)

    days = working_days(start, end)
    if days == 0:
        raise ValidationError(
            {"non_field_errors": ["Cette période ne contient aucun jour ouvré (lundi à vendredi)."]}
        )

    overlap = LeaveRequest.objects.filter(
        employee=user, start_date__lte=end, end_date__gte=start,
    ).exclude(status=LeaveRequest.Status.REFUSED)
    if overlap.exists():
        raise ValidationError({"non_field_errors": ["Une demande existe déjà sur cette période."]})

    if leave_type == LeaveRequest.LeaveType.PAID:
        remaining = paid_balance(user, start)["remaining"]
        if days > remaining:
            raise ValidationError({
                "non_field_errors": [
                    f"Solde insuffisant : {days} jours demandés, votre solde est de {remaining} jours."
                ]
            })
    return days
