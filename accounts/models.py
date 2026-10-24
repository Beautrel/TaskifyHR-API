from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError("L'adresse e-mail est obligatoire.")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("role", User.Role.MANAGER)
        return self.create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    """Employé ou manager. La connexion se fait par adresse e-mail."""

    class Role(models.TextChoices):
        EMPLOYEE = "employee", "Employé"
        MANAGER = "manager", "Manager"

    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=150)
    employee_id = models.CharField("matricule", max_length=20, unique=True)
    phone = models.CharField(max_length=20, blank=True, default="")
    team = models.CharField(max_length=100, default="Équipe Produit")
    job_title = models.CharField(max_length=100, default="Employé")
    contract = models.CharField(max_length=30, default="CDI")
    weekly_hours = models.PositiveSmallIntegerField(default=35)
    arrival_date = models.DateField(default=timezone.localdate)
    annual_leave_days = models.PositiveSmallIntegerField(default=20)

    # Contrôle d'accès par rôle (RBAC)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.EMPLOYEE)
    manager = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="reports"
    )

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name", "employee_id"]

    objects = UserManager()

    class Meta:
        ordering = ["full_name"]

    def __str__(self):
        return f"{self.full_name} ({self.employee_id})"

    @property
    def is_manager(self) -> bool:
        return self.role == self.Role.MANAGER

    @property
    def first_name(self) -> str:
        return self.full_name.split(" ")[0] if self.full_name else ""
