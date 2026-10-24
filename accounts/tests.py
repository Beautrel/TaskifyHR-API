from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from taskify_api.testing import freeze_today

from .models import User

PASSWORD = "Taskify2026!"
VALID = {"full_name": "Paul Durand", "email": "paul.durand@taskify.fr",
         "employee_id": "tf-100", "password": "Bonjour2026abc"}


class RegisterTests(APITestCase):
    def setUp(self):
        freeze_today(self)
        cache.clear()
        self.manager = User.objects.create_user(
            "sophie@taskify.fr", PASSWORD, full_name="Sophie Bernard", employee_id="TF-007",
            role=User.Role.MANAGER, team="Équipe Produit")

    def test_register_creates_employee_attached_to_manager(self):
        r = self.client.post("/api/auth/register/", VALID, format="json")
        self.assertEqual(r.status_code, 201)
        user = User.objects.get(email="paul.durand@taskify.fr")
        self.assertEqual(user.employee_id, "TF-100")           # normalisé en majuscules
        self.assertEqual(user.role, User.Role.EMPLOYEE)
        self.assertEqual(user.manager, self.manager)
        self.assertNotEqual(user.password, VALID["password"])  # jamais en clair
        self.assertNotIn("password", r.data)

    def test_password_rules(self):
        cases = {"Court1": "12 caractères minimum.",
                 "bonjour2026abc": "Ajoutez une majuscule.",
                 "BonjourBonjour": "Ajoutez un chiffre."}
        for password, message in cases.items():
            r = self.client.post("/api/auth/register/", {**VALID, "password": password}, format="json")
            self.assertEqual(r.status_code, 400, password)
            self.assertIn(message, r.data["password"], password)

    def test_duplicate_email_and_employee_id(self):
        self.client.post("/api/auth/register/", VALID, format="json")
        r = self.client.post("/api/auth/register/", {**VALID, "employee_id": "TF-101"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("email", r.data)
        r = self.client.post("/api/auth/register/", {**VALID, "email": "autre@taskify.fr"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("Ce matricule est déjà utilisé.", r.data["employee_id"])

    def test_invalid_employee_id_and_name(self):
        r = self.client.post("/api/auth/register/", {**VALID, "employee_id": "42"}, format="json")
        self.assertIn("Format attendu : TF-042.", r.data["employee_id"])
        r = self.client.post("/api/auth/register/", {**VALID, "full_name": "Paul"}, format="json")
        self.assertIn("full_name", r.data)


class LoginAndProfileTests(APITestCase):
    def setUp(self):
        freeze_today(self)
        cache.clear()
        self.user = User.objects.create_user(
            "lea@taskify.fr", PASSWORD, full_name="Léa Martin", employee_id="TF-042", phone="06 12 34 56 78")

    def test_login_returns_tokens_and_profile(self):
        r = self.client.post("/api/auth/login/", {"email": "lea@taskify.fr", "password": PASSWORD}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertIn("access", r.data)
        self.assertIn("refresh", r.data)
        self.assertEqual(r.data["user"]["first_name"], "Léa")
        self.assertFalse(r.data["user"]["is_manager"])

    def test_wrong_password_gives_french_message(self):
        r = self.client.post("/api/auth/login/", {"email": "lea@taskify.fr", "password": "faux"}, format="json")
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.data["detail"], "Adresse e-mail ou mot de passe incorrect.")

    def test_me_requires_authentication(self):
        self.assertEqual(self.client.get("/api/me/").status_code, 401)

    def test_token_gives_access_to_me(self):
        token = self.client.post("/api/auth/login/", {"email": "lea@taskify.fr", "password": PASSWORD},
                                 format="json").data["access"]
        r = self.client.get("/api/me/", HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["email"], "lea@taskify.fr")

    def test_only_phone_is_editable(self):
        self.client.force_authenticate(self.user)
        r = self.client.patch("/api/me/", {"phone": "699353665", "full_name": "Pirate", "role": "manager"},
                              format="json")
        self.assertEqual(r.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.phone, "699353665")
        self.assertEqual(self.user.full_name, "Léa Martin")
        self.assertEqual(self.user.role, User.Role.EMPLOYEE)

    def test_invalid_phone_is_refused(self):
        self.client.force_authenticate(self.user)
        r = self.client.patch("/api/me/", {"phone": "abc"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("Saisissez un numéro de téléphone valide.", r.data["phone"])

    @override_settings(REST_FRAMEWORK={
        "DEFAULT_AUTHENTICATION_CLASSES": ("rest_framework_simplejwt.authentication.JWTAuthentication",),
        "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
        "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
        "URL_FORMAT_OVERRIDE": None,
        "DEFAULT_THROTTLE_RATES": {"login": "2/min", "register": "20/min"},
    })
    def test_login_is_rate_limited(self):
        from rest_framework.throttling import ScopedRateThrottle
        ScopedRateThrottle.THROTTLE_RATES = {"login": "2/min", "register": "20/min"}
        try:
            codes = [self.client.post("/api/auth/login/", {"email": "lea@taskify.fr", "password": "x"},
                                      format="json").status_code for _ in range(4)]
        finally:
            ScopedRateThrottle.THROTTLE_RATES = {"login": "20/min", "register": "20/min"}
            cache.clear()
        self.assertIn(429, codes)
