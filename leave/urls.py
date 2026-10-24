from django.urls import path

from . import views

urlpatterns = [
    path("leave/balance/", views.BalanceView.as_view(), name="leave-balance"),
    path("leave/requests/", views.MyRequestsView.as_view(), name="leave-requests"),
    path("manager/approvals/", views.ApprovalsView.as_view(), name="manager-approvals"),
    path("manager/requests/", views.TeamRequestsView.as_view(), name="manager-requests"),
    path("manager/requests/<uuid:pk>/approve/", views.ApproveView.as_view(), name="manager-approve"),
    path("manager/requests/<uuid:pk>/refuse/", views.RefuseView.as_view(), name="manager-refuse"),
    path("manager/report/", views.ReportView.as_view(), name="manager-report"),
    path("manager/report/export/", views.ReportExportView.as_view(), name="manager-report-export"),
]
