from django.contrib import admin

from .models import User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("full_name", "email", "employee_id", "role", "team", "manager")
    list_filter = ("role", "team")
    search_fields = ("full_name", "email", "employee_id")
    exclude = ("password", "groups", "user_permissions")
