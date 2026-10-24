from django.contrib import admin

from .models import Attendance, WorkSite


@admin.register(WorkSite)
class WorkSiteAdmin(admin.ModelAdmin):
    list_display = ("name", "latitude", "longitude", "radius_m")


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ("employee", "date", "clock_in", "clock_out")
    list_filter = ("date",)
