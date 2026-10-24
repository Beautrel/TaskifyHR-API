import uuid

from django.conf import settings
from django.db import models


class LeaveRequest(models.Model):
    class LeaveType(models.TextChoices):
        PAID = "Congés payés", "Congés payés"        # consomme le solde
        UNPAID = "Congé sans solde", "Congé sans solde"

    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        APPROVED = "approved", "Approuvé"
        REFUSED = "refused", "Refusé"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="leave_requests"
    )
    leave_type = models.CharField(max_length=30, choices=LeaveType.choices, default=LeaveType.PAID)
    start_date = models.DateField()
    end_date = models.DateField()
    days = models.PositiveSmallIntegerField(help_text="Jours ouvrés (lundi à vendredi), calculés par le serveur.")
    reason = models.CharField(max_length=200, blank=True, default="")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="decided_requests",
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    refusal_reason = models.CharField(max_length=300, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["employee", "start_date"])]

    def __str__(self):
        return f"{self.employee.full_name} {self.start_date} → {self.end_date} ({self.status})"
