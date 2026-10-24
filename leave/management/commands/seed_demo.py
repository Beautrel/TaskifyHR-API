"""Données de démonstration, identiques à celles des services simulés de l'application mobile.

    python manage.py seed_demo          # crée les données (ne duplique rien)
    python manage.py seed_demo --reset  # supprime les données de démonstration puis les recrée
"""
from datetime import date

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import User
from attendance.services import default_site
from leave.models import LeaveRequest

PASSWORD = "Taskify2026!"


class Command(BaseCommand):
    help = "Crée les comptes et les demandes de démonstration."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Supprime les données de démonstration avant de les recréer.")

    @transaction.atomic
    def handle(self, *args, **options):
        emails = ["sophie.bernard@taskify.fr", "lea.martin@taskify.fr", "hugo.petit@taskify.fr"]
        if options["reset"]:
            User.objects.filter(email__in=emails).delete()

        sophie, _ = User.objects.get_or_create(
            email="sophie.bernard@taskify.fr",
            defaults=dict(full_name="Sophie Bernard", employee_id="TF-007", role=User.Role.MANAGER,
                          job_title="Responsable produit", phone="06 98 76 54 32",
                          arrival_date=date(2022, 9, 1)),
        )
        lea, _ = User.objects.get_or_create(
            email="lea.martin@taskify.fr",
            defaults=dict(full_name="Léa Martin", employee_id="TF-042", manager=sophie,
                          job_title="Développeuse", phone="06 12 34 56 78",
                          arrival_date=date(2025, 6, 2)),
        )
        hugo, _ = User.objects.get_or_create(
            email="hugo.petit@taskify.fr",
            defaults=dict(full_name="Hugo Petit", employee_id="TF-051", manager=sophie,
                          job_title="Développeur", phone="06 55 44 33 22",
                          arrival_date=date(2024, 3, 11)),
        )
        for user in (sophie, lea, hugo):
            user.set_password(PASSWORD)
            user.save()

        P, A = LeaveRequest.Status.PENDING, LeaveRequest.Status.APPROVED
        paid = LeaveRequest.LeaveType.PAID
        demo = [
            (lea, date(2026, 10, 19), date(2026, 10, 21), 3, "Repos personnel", P, None),
            (lea, date(2026, 8, 5), date(2026, 8, 14), 8, "Vacances", A, sophie),
            (hugo, date(2026, 10, 26), date(2026, 10, 27), 2, "Rendez-vous privé", P, None),
            (hugo, date(2026, 7, 27), date(2026, 8, 13), 14, "Vacances", A, sophie),
        ]
        created = 0
        for employee, start, end, days, reason, status, decided_by in demo:
            _, was_created = LeaveRequest.objects.get_or_create(
                employee=employee, start_date=start, end_date=end,
                defaults=dict(days=days, reason=reason, leave_type=paid, status=status, decided_by=decided_by),
            )
            created += was_created

        default_site()  # crée le lieu de travail par défaut s'il n'existe pas
        self.stdout.write(self.style.SUCCESS(
            f"Données de démonstration prêtes ({created} demande(s) créée(s)). "
            f"Mot de passe commun : {PASSWORD}"
        ))
