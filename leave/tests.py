from datetime import date, timedelta

from django.core.cache import cache
from rest_framework.test import APITestCase

from accounts.models import User
from attendance.models import Attendance
from taskify_api.testing import FIXED_TODAY, freeze_today, monday

from . import services
from .models import LeaveRequest

PASSWORD = "Taskify2026!"


def make_users():
    boss = User.objects.create_user("boss@taskify.fr", PASSWORD, full_name="Sophie Bernard",
                                    employee_id="TF-007", role=User.Role.MANAGER)
    emp = User.objects.create_user("lea@taskify.fr", PASSWORD, full_name="Léa Martin",
                                   employee_id="TF-042", manager=boss)
    return boss, emp


class BaseApiTest(APITestCase):
    def setUp(self):
        freeze_today(self)
        cache.clear()
        self.boss, self.emp = make_users()

    def as_user(self, user):
        self.client.force_authenticate(user)

    def create_request(self, start, end, leave_type="Congés payés", user=None):
        self.as_user(user or self.emp)
        return self.client.post("/api/leave/requests/", {
            "start_date": start.isoformat(), "end_date": end.isoformat(), "leave_type": leave_type,
            "reason": "Test"}, format="json")


class WorkingDaysTests(APITestCase):
    def test_weekends_are_excluded(self):
        self.assertEqual(services.working_days(monday(1), monday(1) + timedelta(days=2)), 3)   # lun-mer
        self.assertEqual(services.working_days(monday(1), monday(1) + timedelta(days=6)), 5)   # lun-dim
        self.assertEqual(services.working_days(monday(1) + timedelta(days=5), monday(1) + timedelta(days=6)), 0)

    def test_leave_period_runs_june_to_may(self):
        self.assertEqual(services.leave_period(date(2026, 10, 12))[2], "juin 2026 – mai 2027")
        self.assertEqual(services.leave_period(date(2027, 5, 31))[2], "juin 2026 – mai 2027")
        self.assertEqual(services.leave_period(date(2027, 6, 1))[2], "juin 2027 – mai 2028")


class CreateRequestTests(BaseApiTest):
    def test_valid_request_computes_days_server_side(self):
        r = self.create_request(monday(1), monday(1) + timedelta(days=2))
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["days"], 3)
        self.assertEqual(r.data["status"], "pending")
        self.assertEqual(r.data["employee_name"], "Léa Martin")

    def test_start_must_be_in_the_future(self):
        r = self.create_request(FIXED_TODAY, FIXED_TODAY + timedelta(days=1))
        self.assertEqual(r.status_code, 400)
        self.assertIn("La date de début doit être future.", r.data["start_date"])

    def test_end_must_not_precede_start(self):
        r = self.create_request(monday(2), monday(1))
        self.assertEqual(r.status_code, 400)
        self.assertIn("La fin doit être après le début.", r.data["end_date"])

    def test_weekend_only_period_is_refused(self):
        saturday = monday(1) + timedelta(days=5)
        r = self.create_request(saturday, saturday + timedelta(days=1))
        self.assertEqual(r.status_code, 400)
        self.assertIn("aucun jour ouvré", r.data["non_field_errors"][0])

    def test_overlap_is_refused_but_refused_requests_do_not_block(self):
        first = self.create_request(monday(1), monday(1) + timedelta(days=2))
        self.assertEqual(first.status_code, 201)
        r = self.create_request(monday(1) + timedelta(days=1), monday(1) + timedelta(days=3))
        self.assertEqual(r.status_code, 400)
        self.assertIn("Une demande existe déjà sur cette période.", r.data["non_field_errors"])

        LeaveRequest.objects.filter(pk=first.data["id"]).update(status="refused")
        again = self.create_request(monday(1) + timedelta(days=1), monday(1) + timedelta(days=3))
        self.assertEqual(again.status_code, 201)

    def test_paid_leave_cannot_exceed_balance_but_unpaid_can(self):
        long_end = monday(1) + timedelta(weeks=5)       # 26 jours ouvrés > 20
        r = self.create_request(monday(1), long_end)
        self.assertEqual(r.status_code, 400)
        self.assertIn("Solde insuffisant", r.data["non_field_errors"][0])
        ok = self.create_request(monday(1), long_end, leave_type="Congé sans solde")
        self.assertEqual(ok.status_code, 201)

    def test_authentication_required(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/leave/requests/").status_code, 401)

    def test_employee_only_sees_own_requests(self):
        self.create_request(monday(1), monday(1) + timedelta(days=1))
        other = User.objects.create_user("hugo@taskify.fr", PASSWORD, full_name="Hugo Petit",
                                         employee_id="TF-051", manager=self.boss)
        self.as_user(other)
        r = self.client.get("/api/leave/requests/")
        self.assertEqual(len(r.data["results"] if "results" in r.data else r.data), 0)


class ManagerWorkflowTests(BaseApiTest):
    def make_pending(self, start, end):
        r = self.create_request(start, end)
        self.assertEqual(r.status_code, 201, r.data)
        return r.data["id"]

    def test_balance_is_deducted_only_on_approval(self):
        rid = self.make_pending(monday(1), monday(1) + timedelta(days=2))
        self.as_user(self.emp)
        before = self.client.get("/api/leave/balance/").data
        self.assertEqual((before["acquired"], before["used"], before["pending"], before["remaining"]),
                         (20, 0, 3, 20))

        self.as_user(self.boss)
        self.assertEqual(self.client.post(f"/api/manager/requests/{rid}/approve/").status_code, 200)
        self.as_user(self.emp)
        after = self.client.get("/api/leave/balance/").data
        self.assertEqual((after["used"], after["pending"], after["remaining"]), (3, 0, 17))
        self.assertEqual(after["period"], "juin 2026 – mai 2027")

    def test_refusal_requires_a_reason_and_does_not_deduct(self):
        rid = self.make_pending(monday(1), monday(1) + timedelta(days=1))
        self.as_user(self.boss)
        r = self.client.post(f"/api/manager/requests/{rid}/refuse/", {"reason": "   "}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("Le motif du refus est obligatoire.", r.data["reason"])

        r = self.client.post(f"/api/manager/requests/{rid}/refuse/",
                             {"reason": "Présence requise pour la livraison."}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["status"], "refused")
        self.assertEqual(r.data["refusal_reason"], "Présence requise pour la livraison.")
        self.as_user(self.emp)
        self.assertEqual(self.client.get("/api/leave/balance/").data["remaining"], 20)

    def test_balance_is_rechecked_at_decision_time(self):
        # Deux demandes de 12 jours : chacune passe seule (les jours en attente ne sont pas déduits)
        a = self.make_pending(monday(1), monday(1) + timedelta(days=15))   # 12 jours ouvrés
        b = self.make_pending(monday(6), monday(6) + timedelta(days=15))
        self.as_user(self.boss)
        self.assertEqual(self.client.post(f"/api/manager/requests/{a}/approve/").status_code, 200)
        r = self.client.post(f"/api/manager/requests/{b}/approve/")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["detail"], "Solde insuffisant : la demande ne peut plus être approuvée.")

    def test_request_cannot_be_decided_twice(self):
        rid = self.make_pending(monday(1), monday(1) + timedelta(days=1))
        self.as_user(self.boss)
        self.client.post(f"/api/manager/requests/{rid}/approve/")
        r = self.client.post(f"/api/manager/requests/{rid}/refuse/", {"reason": "Trop tard"}, format="json")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["detail"], "Cette demande a déjà été traitée.")

    def test_rbac_employees_cannot_use_manager_endpoints(self):
        rid = self.make_pending(monday(1), monday(1) + timedelta(days=1))
        self.as_user(self.emp)
        self.assertEqual(self.client.get("/api/manager/approvals/").status_code, 403)
        self.assertEqual(self.client.post(f"/api/manager/requests/{rid}/approve/").status_code, 403)
        self.assertEqual(self.client.get("/api/manager/report/").status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/manager/approvals/").status_code, 401)

    def test_a_manager_only_sees_and_decides_for_their_own_team(self):
        rid = self.make_pending(monday(1), monday(1) + timedelta(days=1))
        other_boss = User.objects.create_user("autre@taskify.fr", PASSWORD, full_name="Marc Autre",
                                              employee_id="TF-008", role=User.Role.MANAGER)
        self.as_user(other_boss)
        data = self.client.get("/api/manager/approvals/").data
        self.assertEqual(len(data["results"] if "results" in data else data), 0)
        self.assertEqual(self.client.post(f"/api/manager/requests/{rid}/approve/").status_code, 404)

    def test_approvals_list_shows_employee_balance(self):
        self.make_pending(monday(1), monday(1) + timedelta(days=2))
        self.as_user(self.boss)
        data = self.client.get("/api/manager/approvals/").data
        rows = data["results"] if "results" in data else data
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["employee_name"], "Léa Martin")
        self.assertEqual(rows[0]["employee_remaining"], 20)


class ExportTests(BaseApiTest):
    def setUp(self):
        super().setUp()
        start = date(2026, 10, 19)
        self.create_request(start, start + timedelta(days=2))
        Attendance.objects.create(
            employee=self.emp, date=date(2026, 10, 6),
            clock_in=__import__("datetime").datetime(2026, 10, 6, 7, 0, tzinfo=__import__("datetime").timezone.utc),
            clock_out=__import__("datetime").datetime(2026, 10, 6, 15, 30, tzinfo=__import__("datetime").timezone.utc))
        self.as_user(self.boss)

    def test_report_preview(self):
        r = self.client.get("/api/manager/report/?month=2026-10")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["title"], "Octobre 2026")
        self.assertEqual(r.data["pending_days"], 3)
        self.assertEqual(r.data["leave_lines"][0]["employee"], "Léa Martin")
        self.assertEqual(r.data["attendance_lines"][0]["hours"], 8.5)

    def test_only_days_inside_the_month_are_counted(self):
        # demande du 29 oct. au 3 nov. : 3 jours ouvrés en octobre (jeu, ven + ... ) calculés sur le mois seulement
        LeaveRequest.objects.create(employee=self.emp, start_date=date(2026, 10, 29), end_date=date(2026, 11, 3),
                                    days=4, leave_type="Congé sans solde")
        rows = self.client.get("/api/manager/report/?month=2026-10").data["leave_lines"]
        line = [l for l in rows if l["start_date"] == date(2026, 10, 29)][0]
        self.assertEqual(line["working_days_in_month"], 2)   # jeudi 29 et vendredi 30

    def test_csv_export(self):
        r = self.client.get("/api/manager/report/export/?month=2026-10&format=csv")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/csv", r["Content-Type"])
        text = r.content.decode("utf-8-sig")
        self.assertIn("Employé;Type;Début;Fin;Jours ouvrés dans le mois;Statut", text)
        self.assertIn("Léa Martin;Congés payés;19/10/2026;21/10/2026;3;En attente", text)
        self.assertIn("Léa Martin;06/10/2026", text)

    def test_pdf_export_is_a_valid_pdf(self):
        r = self.client.get("/api/manager/report/export/?month=2026-10&format=pdf")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertTrue(r.content.startswith(b"%PDF-1.4"))
        self.assertTrue(r.content.rstrip().endswith(b"%%EOF"))

    def test_invalid_month_and_format(self):
        self.assertEqual(self.client.get("/api/manager/report/?month=octobre").status_code, 400)
        self.assertEqual(self.client.get("/api/manager/report/export/?format=xls").status_code, 400)


class TeamRequestsEndpointTests(APITestCase):
    """GET /api/manager/requests/ : toutes les demandes de l'équipe, réservé au manager."""

    def test_manager_sees_team_requests_and_employee_is_forbidden(self):
        from django.core.management import call_command
        from rest_framework.test import APIClient
        call_command("seed_demo", verbosity=0)
        client = APIClient()
        login = lambda e: client.post("/api/auth/login/", {"email": e, "password": "Taskify2026!"}, format="json").json()["access"]
        client.credentials(HTTP_AUTHORIZATION="Bearer " + login("sophie.bernard@taskify.fr"))
        r = client.get("/api/manager/requests/")
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(len(r.json()), 4)
        client.credentials(HTTP_AUTHORIZATION="Bearer " + login("lea.martin@taskify.fr"))
        self.assertEqual(client.get("/api/manager/requests/").status_code, 403)
