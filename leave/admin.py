from django.contrib import admin

from .models import LeaveRequest


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ("employee", "leave_type", "start_date", "end_date", "days", "status", "decided_by")
    list_filter = ("status", "leave_type")
    search_fields = ("employee__full_name", "employee__email")
