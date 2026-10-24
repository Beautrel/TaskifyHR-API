from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from accounts.models import User
from taskify_api.testing import freeze_today

from .models import Attendance
from .services import distance_m

SITE = {"latitude": 4.0511, "longitude": 9.7679}
FAR = {"latitude": 4.0700, "longitude": 9.7900}   # à environ 3 km du lieu de travail


class AttendanceTests(APITestCase):
    def setUp(self):
        freeze_today(self)
        cache.clear()
        self.user = User.objects.create_user("lea@taskify.fr", "Taskify2026!", full_name="Léa Martin",
                                             employee_id="TF-042")
        self.client.force_authenticate(self.user)

    def test_distance_is_in_meters(self):
        self.assertAlmostEqual(distance_m(4.0511, 9.7679, 4.0511, 9.7679), 0, places=3)
        self.assertGreater(distance_m(4.0511, 9.7679, 4.0700, 9.7900), 2000)

    def test_today_before_entry(self):
        r = self.client.get("/api/attendance/today/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["status"], "before_entry")
        self.assertIsNone(r.data["clock_in"])

    def test_full_day(self):
        r = self.client.post("/api/attendance/clock-in/", SITE, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["status"], "in_progress")
        self.assertEqual(self.client.get("/api/attendance/today/").data["status"], "in_progress")

        r = self.client.post("/api/attendance/clock-out/", SITE, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["status"], "done")
        self.assertIsNotNone(r.data["clock_out_time"])

    def test_one_entry_and_one_exit_per_day(self):
        self.client.post("/api/attendance/clock-in/", SITE, format="json")
        r = self.client.post("/api/attendance/clock-in/", SITE, format="json")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "already_clocked_in")

        self.client.post("/api/attendance/clock-out/", SITE, format="json")
        r = self.client.post("/api/attendance/clock-out/", SITE, format="json")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "already_clocked_out")
        self.assertEqual(Attendance.objects.filter(employee=self.user).count(), 1)

    def test_exit_requires_an_entry(self):
        r = self.client.post("/api/attendance/clock-out/", SITE, format="json")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "no_clock_in")

    def test_outside_the_zone_is_refused(self):
        r = self.client.post("/api/attendance/clock-in/", FAR, format="json")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.data["code"], "out_of_zone")
        self.assertFalse(Attendance.objects.exists())

    def test_position_is_required(self):
        r = self.client.post("/api/attendance/clock-in/", {}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["code"], "position_required")

    def test_zone_check_can_be_disabled_for_demos(self):
        from django.conf import settings
        config = {**settings.TASKIFY, "ENFORCE_ZONE": False}
        with override_settings(TASKIFY=config):
            r = self.client.post("/api/attendance/clock-in/", FAR, format="json")
        self.assertEqual(r.status_code, 201)

    def test_authentication_required(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/attendance/today/").status_code, 401)
        self.assertEqual(self.client.post("/api/attendance/clock-in/", SITE, format="json").status_code, 401)


class SchemaTests(APITestCase):
    def test_openapi_schema_is_served(self):
        r = self.client.get("/api/schema/")
        self.assertEqual(r.status_code, 200)
