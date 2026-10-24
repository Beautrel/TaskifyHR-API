from django.urls import path

from . import views

urlpatterns = [
    path("attendance/today/", views.TodayView.as_view(), name="attendance-today"),
    path("attendance/clock-in/", views.ClockInView.as_view(), name="attendance-clock-in"),
    path("attendance/clock-out/", views.ClockOutView.as_view(), name="attendance-clock-out"),
]
