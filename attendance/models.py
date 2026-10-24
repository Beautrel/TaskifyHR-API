from django.conf import settings
from django.db import models


class WorkSite(models.Model):
    """Lieu de travail : le pointage n'est accepté que dans son rayon."""

    name = models.CharField(max_length=100)
    latitude = models.FloatField()
    longitude = models.FloatField()
    radius_m = models.PositiveIntegerField(default=200)

    def __str__(self):
        return self.name


class Attendance(models.Model):
    """Pointage d'une journée : une seule entrée et une seule sortie par jour."""

    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="attendances"
    )
    date = models.DateField()
    clock_in = models.DateTimeField()
    clock_out = models.DateTimeField(null=True, blank=True)
    in_latitude = models.FloatField(null=True, blank=True)
    in_longitude = models.FloatField(null=True, blank=True)
    out_latitude = models.FloatField(null=True, blank=True)
    out_longitude = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(fields=["employee", "date"], name="one_attendance_per_day"),
        ]

    def __str__(self):
        return f"{self.employee.full_name} {self.date}"

    @property
    def worked_hours(self):
        if not self.clock_out:
            return None
        return round((self.clock_out - self.clock_in).total_seconds() / 3600, 2)
