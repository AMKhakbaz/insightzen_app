"""URL declarations for the core application.

This module maps URL patterns to view functions for all user facing
functionality, including authentication, dashboard, project management
and user management. Keeping URL patterns within this app makes it
simple to see at a glance how different parts of the application are
accessible.
"""

from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
# Import enhanced performance views separately to avoid circular import issues
from . import views_performance as perf

urlpatterns = [
    # Authentication
    path('login/', views.login_view, name='login'),
    # Custom logout using our own view to ensure session termination
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register, name='register'),
    path('payment/', views.payment, name='payment'),
    path('superadmin/', views.superadmin_dashboard, name='superadmin_dashboard'),
    # Language toggle
    path('lang/<str:lang>/', views.toggle_language, name='toggle_language'),
    # Home dashboard
    path('', views.home, name='home'),
    path('api/interviewer/dashboard/', views.interviewer_dashboard_data, name='interviewer_dashboard_data'),
    # Project management
    path('projects/', views.project_list, name='project_list'),
    path('projects/add/', views.project_add, name='project_add'),
    path('projects/<int:project_id>/edit/', views.project_edit, name='project_edit'),
    path('projects/<int:project_id>/dataset/append/', views.project_dataset_append, name='project_dataset_append'),
    # Delete project
    path('projects/<int:pk>/delete/', views.project_delete, name='project_delete'),
    # User management
    path('memberships/', views.membership_list, name='membership_list'),
    path('memberships/add/', views.membership_add, name='membership_add'),
    path('memberships/export-workbook/', views.membership_export_workbook, name='membership_export_workbook'),
    path('memberships/import-workbook/', views.membership_import_workbook, name='membership_import_workbook'),
    path('memberships/<int:membership_id>/edit/', views.membership_edit, name='membership_edit'),
    # Delete membership
    path('memberships/<int:pk>/delete/', views.membership_delete, name='membership_delete'),
    path('api/memberships/message/', views.membership_message_send, name='membership_message_send'),

    # Conjoint Analysis
    path('conjoint/', views.conjoint, name='conjoint'),
    path('conjoint/analyze/', views.conjoint_analyze, name='conjoint_analyze'),

    # Coding & Category (Qualitative coding) analysis
    path('coding/', views.coding, name='coding'),
    path('coding/analyze/', views.coding_analyze, name='coding_analyze'),
    path('qc/management/', views.qc_management_view, name='qc_management'),
    path('qc/management/config/', views.qc_management_config, name='qc_management_config'),
    path('qc/management/assign/', views.qc_assignment_assign, name='qc_assignment_assign'),
    path('qc/performance/', views.qc_performance_dashboard, name='qc_performance_dashboard'),
    path('qc/review/', views.qc_review, name='qc_review'),
    path('qc/review/<int:task_id>/', views.qc_review_detail, name='qc_review_detail'),
    path('ai/product-matrix/', views.product_matrix_ai, name='product_matrix_ai'),

    # Quota management
    path('quota/', views.quota_management, name='quota_management'),
    # Telephone interviewer
    path('telephone/', views.telephone_interviewer, name='telephone_interviewer'),
    # Collection performance dashboard and API
    # Collection performance dashboard and API (enhanced)
    path('performance/', perf.collection_performance, name='collection_performance'),
    path('api/performance/', perf.collection_performance_data, name='collection_performance_data'),
    path('api/performance/raw/', perf.collection_performance_raw, name='collection_performance_raw'),
    path('performance/export/', perf.collection_performance_export, name='collection_performance_export'),
    path('api/calendar/events/', views.calendar_events, name='calendar_events'),
    path('api/calendar/events/<int:event_id>/', views.calendar_event_detail, name='calendar_event_detail'),
    path('api/calendar/participants/', views.calendar_participants, name='calendar_participants'),
    path('api/table-filters/<str:table_id>/', views.table_filter_presets, name='table_filter_presets'),
    path('api/table-export/', views.table_export, name='table_export'),
    path('api/notifications/unread/', views.notifications_unread, name='notifications_unread'),
    path('api/notifications/mark-read/', views.notifications_mark_read, name='notifications_mark_read'),

    # Database management
    path('databases/', views.database_list, name='database_list'),
    path('databases/add/', views.database_add, name='database_add'),
    path('databases/<int:pk>/edit/', views.database_edit, name='database_edit'),
    path('databases/<int:pk>/delete/', views.database_delete, name='database_delete'),
    path('databases/<int:pk>/update/', views.database_update, name='database_update'),
    path('databases/<int:pk>/view/', views.database_view, name='database_view'),

    # Quality control editing
    path('qc/edit/', views.qc_edit, name='qc_edit'),
    path('qc/edit/<int:entry_id>/link/', views.qc_edit_link, name='qc_edit_link'),

    # Activity logs (organisation only)
    path('logs/', views.activity_logs, name='activity_logs'),
]