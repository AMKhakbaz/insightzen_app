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
    # Language toggle
    path('lang/<str:lang>/', views.toggle_language, name='toggle_language'),
    # Home dashboard
    path('', views.home, name='home'),
    # Project management
    path('projects/', views.project_list, name='project_list'),
    path('projects/add/', views.project_add, name='project_add'),
    path('projects/<int:project_id>/edit/', views.project_edit, name='project_edit'),
    # Delete project
    path('projects/<int:pk>/delete/', views.project_delete, name='project_delete'),
    # User management
    path('memberships/', views.membership_list, name='membership_list'),
    path('memberships/add/', views.membership_add, name='membership_add'),
    path('projects/<int:project_id>/memberships/bulk/', views.membership_bulk_add, name='membership_bulk_add'),
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