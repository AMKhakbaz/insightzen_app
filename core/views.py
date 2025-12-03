"""Core view functions for InsightZen.

This module implements the primary view logic for the InsightZen
application.  It includes account registration and authentication,
project and membership management and the newly requested panels for
quota management, telephone interviewing and collection performance.
Wherever practical the code attempts to stay close to the latest
database schema and user requirements.  Additional panels such as
Conjoint Analysis or coding are not implemented here but can be added
separately.
"""

from __future__ import annotations

import json
import csv
from datetime import datetime, timedelta
from functools import cmp_to_key
from io import BytesIO, StringIO
from collections import defaultdict
from math import ceil
from typing import Any, Dict, Iterable, List, Tuple, Optional
from types import SimpleNamespace

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Sum, Count, Q, F
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST, require_http_methods
from django.utils import timezone
import random
import re
import psycopg2
from psycopg2 import sql  # type: ignore
from django.conf import settings

# Regular expression used to validate table identifiers passed from the client
_TABLE_ID_PATTERN = re.compile(r'^[A-Za-z0-9_.:-]{1,128}$')


from core.services.database_cache import (
    DatabaseCacheError,
    EnketoLinkError,
    delete_entry_cache,
    infer_columns,
    load_entry_snapshot,
    refresh_entry_cache,
    request_enketo_edit_url,
)
from core.services.persian_dates import calculate_age_from_birth_info
from core.services.notifications import (
    create_notification,
    ensure_project_deadline_notifications,
    localised_message,
    mark_notifications_read,
    notify_custom_message,
    notify_event_invite,
    notify_event_reminder,
    notify_event_update,
    notify_membership_added,
    notify_project_started,
)
try:
    # Optional import for Excel export; if the library is missing the export view
    # will inform the user appropriately.
    import openpyxl  # type: ignore
    from openpyxl.chart import BarChart, Reference  # type: ignore
except Exception:
    openpyxl = None  # type: ignore

from core.services.sample_uploads import (
    SAMPLE_REQUIRED_HEADERS,
    SampleUploadError,
    append_project_respondent_bank,
    append_project_sample_upload,
    ingest_project_sample_upload,
)

PAYMENT_SECURITY_PHRASE = 'Sa00Ad25'
from core.services.call_results import (
    CALL_RESULT_REQUIRED_HEADERS,
    CallResultUploadError,
    clear_project_call_results,
    ingest_project_call_result_upload,
    resolve_call_result_definitions,
)
from core.services.gender_utils import (
    normalize_gender_value,
    gender_value_from_boolean,
    boolean_from_gender_value,
)
from core.services.membership_workbook import (
    MembershipWorkbookError,
    export_memberships_workbook,
    import_memberships_workbook,
)

from .forms import (
    LoginForm,
    ProjectForm,
    ProjectSampleAppendForm,
    RegistrationForm,
    UserToProjectForm,
    DatabaseEntryForm,
    MembershipWorkbookForm,
)
from django import forms
from .models import (
    Membership,
    Profile,
    Project,
    Person,
    Mobile,
    Interview,
    Quota,
    ActivityLog,
    CallSample,
    UploadedSampleEntry,
    DatabaseEntry,
    DatabaseEntryEditRequest,
    TableFilterPreset,
    Notification,
    CalendarEvent,
    ReviewTask,
    ReviewRow,
    ReviewAction,
    ChecklistResponse,
)


MEMBERSHIP_PANEL_DEFINITIONS: List[Tuple[str, str, str]] = [
    ('database_management', 'Database Management', 'مدیریت پایگاه داده'),
    ('quota_management', 'Quota Management', 'مدیریت سهمیه'),
    ('collection_management', 'Collection Management', 'مدیریت گردآوری'),
    ('collection_performance', 'Collection Performance', 'کارایی گردآوری'),
    ('telephone_interviewer', 'Telephone Interviewer', 'مصاحبه تلفنی'),
    ('fieldwork_interviewer', 'Fieldwork Interviewer', 'مصاحبه میدانی'),
    ('focus_group_panel', 'Focus Group Panel', 'پنل گروه کانونی'),
    ('qc_management', 'QC Management', 'مدیریت QC'),
    ('qc_performance', 'QC Performance', 'کارایی QC'),
    ('review_data', 'Review Data', 'بازبینی داده'),
    ('edit_data', 'General Edit', 'ویرایش عمومی'),
    ('voice_review', 'Voice Review', 'بازبینی صدا'),
    ('callback_qc', 'Callback QC', 'QC تماس برگشتی'),
    ('coding', 'Coding AI', 'کدگذاری هوش مصنوعی'),
    ('product_matrix_ai', 'Product Matrix AI', 'ماتریس محصول هوش مصنوعی'),
    ('statistical_health_check', 'Statistical Health Check', 'بررسی سلامت آماری'),
    ('tabulation', 'Tabulation', 'جدول‌بندی'),
    ('statistics', 'Statistics', 'آمار'),
    ('funnel_analysis', 'Funnel Analysis', 'تحلیل قیف'),
    ('conjoint_analysis', 'Conjoint Analysis', 'تحلیل همگرایی'),
    ('segmentation_analysis', 'Segmentation Analysis', 'تحلیل تقسیم‌بندی'),
]

MEMBERSHIP_PANEL_FIELDS: List[str] = [field for field, _, _ in MEMBERSHIP_PANEL_DEFINITIONS]

MEMBERSHIP_PANEL_LABELS: Dict[str, str] = {field: label_en for field, label_en, _ in MEMBERSHIP_PANEL_DEFINITIONS}

MEMBERSHIP_PANEL_LABELS_FA: Dict[str, str] = {field: label_fa for field, _, label_fa in MEMBERSHIP_PANEL_DEFINITIONS}


def _bilingual(en_text: str, fa_text: str) -> str:
    """Return a combined English/Persian message string."""

    return f"{en_text} / {fa_text}"


def register(request: HttpRequest) -> HttpResponse:
    """Handle user registration.

    When the submitted form indicates an organisation registration, the
    partially completed user data is stored in the session and the user is
    redirected to a mock payment page.  Otherwise the user and their
    profile are immediately created and the user is sent to the login page.
    """
    if request.user.is_authenticated:
        return redirect('home')

    lang = _get_lang(request)
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            full_name = form.cleaned_data['full_name']
            phone = form.cleaned_data['phone']
            organization = form.cleaned_data['organization']
            password = form.cleaned_data['password']
            if organization:
                # store data temporarily until payment confirmed
                request.session['pending_registration'] = {
                    'email': email,
                    'full_name': full_name,
                    'phone': phone,
                    'organization': True,
                    'password': password,
                }
                return redirect('payment')
            # non‑organisation: create user immediately
            user = User.objects.create_user(username=email, email=email, password=password, first_name=full_name)
            Profile.objects.create(user=user, phone=phone, organization=False)
            messages.success(request, 'Registration successful. You can now log in.')
            return redirect('login')
    else:
        form = RegistrationForm()

    context = {
        'form': form,
        'lang': lang,
        'breadcrumbs': [],
    }
    return render(request, 'register.html', context)


def payment(request: HttpRequest) -> HttpResponse:
    """Simulate a payment gateway for organisation registrations."""
    pending = request.session.get('pending_registration')
    if not pending:
        return redirect('register')

    lang = _get_lang(request)
    context = {
        'security_phrase_value': '',
        'lang': lang,
        'breadcrumbs': _build_breadcrumbs(
            lang,
            (_localise_text(lang, 'Register', 'ثبت‌نام'), reverse('register')),
            (_localise_text(lang, 'Payment', 'پرداخت'), None),
        ),
    }

    if request.method == 'POST':
        security_phrase = request.POST.get('security_phrase', '').strip()
        context['security_phrase_value'] = security_phrase
        if security_phrase != PAYMENT_SECURITY_PHRASE:
            error_message = (
                'عبارت امنیتی نادرست است. لطفاً دوباره تلاش کنید.'
                if lang == 'fa'
                else 'Incorrect security phrase. Please try again.'
            )
            messages.error(request, error_message)
            return render(request, 'payment.html', context)

        email = pending['email']
        full_name = pending['full_name']
        phone = pending['phone']
        password = pending['password']
        # create user and profile as organisation
        user = User.objects.create_user(username=email, email=email, password=password, first_name=full_name)
        Profile.objects.create(user=user, phone=phone, organization=True)
        del request.session['pending_registration']
        messages.success(request, 'Payment successful. Your organisation account has been created.')
        return redirect('login')
    return render(request, 'payment.html', context)


def login_view(request: HttpRequest) -> HttpResponse:
    """Authenticate a user via email and password."""
    if request.user.is_authenticated:
        return redirect('home')
    lang = _get_lang(request)
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']
            user = authenticate(username=email, password=password)
            if user:
                login(request, user)
                return redirect('home')
            messages.error(request, 'Invalid email or password.')
    else:
        form = LoginForm()
    return render(
        request,
        'login.html',
        {
            'form': form,
            'lang': lang,
            'breadcrumbs': [],
        },
    )


def logout_view(request: HttpRequest) -> HttpResponse:
    """Log the user out and redirect to the login page."""
    logout(request)
    return redirect('login')


def toggle_language(request: HttpRequest, lang: str) -> HttpResponse:
    """Switch the interface language between English and Persian."""
    if lang not in ('en', 'fa'):
        lang = 'en'
    request.session['lang'] = lang
    return redirect(request.META.get('HTTP_REFERER', reverse('home')))


@login_required
def home(request: HttpRequest) -> HttpResponse:
    """Display a simple dashboard for the logged in user."""
    profile = getattr(request.user, 'profile', None)
    lang = request.session.get('lang', 'en')
    dashboard_payload = _build_interviewer_dashboard_payload(request.user, lang)
    return render(
        request,
        'home.html',
        {
            'profile': profile,
            'dashboard_payload': dashboard_payload,
            'lang': lang,
        },
    )


def _compute_call_totals(total_calls: int, success_calls: int) -> Tuple[int, float]:
    """Return unsuccessful call count and success rate percentage."""

    failed_calls = max(total_calls - success_calls, 0)
    success_rate = round((success_calls / total_calls) * 100.0, 1) if total_calls else 0.0
    return failed_calls, success_rate


def _build_interviewer_dashboard_payload(
    user: User, lang: str, project_id: Optional[str] | None = None
) -> Dict[str, Any]:
    """Aggregate telephone interviewer metrics for the dashboard."""

    call_qs = Interview.objects.filter(user=user)
    project_stats_qs = call_qs.values('project_id', 'project__name').annotate(
        total_calls=Count('id'), success_calls=Count('id', filter=Q(status=True))
    )

    project_rows: List[Dict[str, Any]] = []
    for idx, row in enumerate(project_stats_qs.order_by('-success_calls', 'project__name')):
        total_calls = int(row['total_calls'])
        success_calls = int(row['success_calls'])
        failed_calls, success_rate = _compute_call_totals(total_calls, success_calls)
        project_rows.append(
            {
                'id': row['project_id'],
                'name': row['project__name'],
                'total_calls': total_calls,
                'success_calls': success_calls,
                'failed_calls': failed_calls,
                'success_rate': success_rate,
                'rank': idx + 1,
            }
        )

    selected_id: Optional[int] = None
    if project_id:
        try:
            parsed = int(project_id)
        except (TypeError, ValueError):
            parsed = None
        if parsed and any(p['id'] == parsed for p in project_rows):
            selected_id = parsed

    filtered_qs = call_qs.filter(project_id=selected_id) if selected_id else call_qs
    total_calls = filtered_qs.count()
    success_calls = filtered_qs.filter(status=True).count()
    failed_calls, success_rate = _compute_call_totals(total_calls, success_calls)

    top_project = project_rows[0] if project_rows else None
    if top_project:
        if lang == 'fa':
            top_summary = (
                f"پروژه برتر: {top_project['name']} (رتبه {top_project['rank']} با "
                f"{top_project['success_calls']} تماس موفق)"
            )
        else:
            top_summary = (
                f"Top project: {top_project['name']} (rank #{top_project['rank']} with "
                f"{top_project['success_calls']} successful calls)"
            )
    else:
        top_summary = (
            'هنوز تماسی ثبت نشده است.'
            if lang == 'fa'
            else 'No call activity has been recorded yet.'
        )

    project_options: List[Dict[str, Any]] = [
        {
            'id': '',
            'name': 'all',
            'label': 'همه پروژه‌ها' if lang == 'fa' else 'All projects',
        }
    ]
    for project in sorted(project_rows, key=lambda p: p['name'] or ''):
        project_options.append({'id': project['id'], 'name': project['name'], 'label': project['name']})

    selected_label = project_options[0]['label']
    if selected_id:
        for opt in project_options:
            if opt['id'] == selected_id:
                selected_label = opt['label']
                break

    payload: Dict[str, Any] = {
        'summary': {
            'total_calls': total_calls,
            'success_calls': success_calls,
            'failed_calls': failed_calls,
            'success_rate': success_rate,
        },
        'chart': {
            'success_calls': success_calls,
            'failed_calls': failed_calls,
            'success_percentage': success_rate,
            'failed_percentage': round(100.0 - success_rate, 1) if total_calls else 0.0,
        },
        'projects': project_rows,
        'project_options': project_options,
        'selected_project': selected_id,
        'selected_label': selected_label,
        'top_summary': top_summary,
        'labels': {
            'success': 'تماس موفق' if lang == 'fa' else 'Successful calls',
            'unsuccessful': 'ناموفق' if lang == 'fa' else 'Unsuccessful',
        },
    }
    return payload


@login_required
def interviewer_dashboard_data(request: HttpRequest) -> JsonResponse:
    """Expose telephone interviewer totals for the current user as JSON."""

    lang = request.session.get('lang', 'en')
    project_id = request.GET.get('project')
    payload = _build_interviewer_dashboard_payload(request.user, lang, project_id)
    return JsonResponse(payload)


@login_required
def superadmin_dashboard(request: HttpRequest) -> HttpResponse:
    """Display an overview dashboard for super administrators."""

    user = request.user
    lang = _get_lang(request)
    if not getattr(user, 'is_superuser', False):
        messages.error(request, 'Access denied: super admin privileges are required.')
        return redirect('home')

    today = timezone.now().date()
    upcoming_window = today + timedelta(days=14)

    overdue_qs = Project.objects.filter(deadline__lt=today).order_by('deadline')
    starting_soon_qs = (
        Project.objects.filter(start_date__gt=today, start_date__lte=upcoming_window)
        .order_by('start_date')
    )
    ownerless_qs = (
        Project.objects.annotate(
            owner_count=Count('memberships', filter=Q(memberships__is_owner=True))
        )
        .filter(owner_count=0)
        .order_by('deadline')
    )
    zero_quota_qs = (
        Project.objects.annotate(quota_count=Count('quotas'))
        .filter(quota_count=0)
        .order_by('deadline')
    )
    zero_membership_qs = (
        Project.objects.annotate(member_count=Count('memberships'))
        .filter(member_count=0)
        .order_by('deadline')
    )

    stats = {
        'projects_total': Project.objects.count(),
        'projects_active': Project.objects.filter(deadline__gte=today).count(),
        'projects_overdue': overdue_qs.count(),
        'projects_starting_soon': starting_soon_qs.count(),
        'projects_missing_owner': ownerless_qs.count(),
        'projects_missing_quota': zero_quota_qs.count(),
        'memberships_total': Membership.objects.count(),
        'respondents_total': Person.objects.count(),
        'mobiles_total': Mobile.objects.count(),
        'organisations_total': Profile.objects.filter(organization=True).count(),
        'unread_notifications': Notification.objects.filter(is_read=False).count(),
    }

    overdue_projects = list(overdue_qs[:10])
    starting_soon_projects = list(starting_soon_qs[:10])
    ownerless_projects = list(ownerless_qs[:10])
    zero_quota_projects = list(zero_quota_qs[:10])
    zero_membership_projects = list(zero_membership_qs[:10])

    attention_map: Dict[int, Dict[str, Any]] = {}

    def _track_attention(
        projects: Iterable[Project],
        reason_en: str,
        reason_fa: str,
        severity: str = 'info',
    ) -> None:
        for project in projects:
            entry = attention_map.setdefault(
                project.pk,
                {
                    'project': project,
                    'reasons': [],
                    'severity': 'info',
                },
            )
            entry['reasons'].append({'en': reason_en, 'fa': reason_fa})
            if severity == 'danger':
                entry['severity'] = 'danger'
            elif severity == 'warning' and entry['severity'] != 'danger':
                entry['severity'] = 'warning'

    _track_attention(overdue_projects, 'Deadline passed', 'ددلاین گذشته است', 'danger')
    _track_attention(starting_soon_projects, 'Starts within 2 weeks', 'شروع در دو هفته آینده', 'info')
    _track_attention(ownerless_projects, 'No owner assigned', 'مالک تعیین نشده است', 'warning')
    _track_attention(zero_quota_projects, 'No quotas configured', 'سهمیه‌ای تعریف نشده است', 'warning')
    _track_attention(
        zero_membership_projects,
        'No team members yet',
        'هیچ عضوی ثبت نشده است',
        'info',
    )

    projects_attention = sorted(
        attention_map.values(),
        key=lambda entry: (entry['project'].deadline, entry['project'].start_date),
    )[:10]

    alert_collections = [
        {
            'key': 'owner_gaps',
            'label_en': 'Projects without an owner',
            'label_fa': 'پروژه بدون مالک',
            'count': stats['projects_missing_owner'],
            'items': ownerless_projects[:4],
        },
        {
            'key': 'quota_gaps',
            'label_en': 'Projects without quotas',
            'label_fa': 'پروژه بدون سهمیه',
            'count': stats['projects_missing_quota'],
            'items': zero_quota_projects[:4],
        },
        {
            'key': 'member_gaps',
            'label_en': 'Projects without team members',
            'label_fa': 'پروژه بدون اعضا',
            'count': zero_membership_qs.count(),
            'items': zero_membership_projects[:4],
        },
        {
            'key': 'overdue',
            'label_en': 'Overdue deadlines',
            'label_fa': 'ددلاین‌های گذشته',
            'count': stats['projects_overdue'],
            'items': overdue_projects[:4],
        },
    ]

    quick_actions = [
        {
            'icon': 'layers',
            'label_en': 'Projects',
            'label_fa': 'پروژه‌ها',
            'description_en': 'Review, edit, or archive studies.',
            'description_fa': 'پروژه‌های در حال اجرا را بررسی و ویرایش کنید.',
            'url': reverse('project_list'),
        },
        {
            'icon': 'users',
            'label_en': 'Memberships',
            'label_fa': 'اعضا',
            'description_en': 'Manage project owners and panel access.',
            'description_fa': 'مالکین و دسترسی به پنل‌ها را مدیریت کنید.',
            'url': reverse('membership_list'),
        },
        {
            'icon': 'database',
            'label_en': 'Databases',
            'label_fa': 'پایگاه‌های داده',
            'description_en': 'Maintain respondent databases.',
            'description_fa': 'پایگاه داده پاسخگویان را نگهداری کنید.',
            'url': reverse('database_list'),
        },
        {
            'icon': 'bell',
            'label_en': 'Notifications',
            'label_fa': 'اعلان‌ها',
            'description_en': 'Jump to the global notification center.',
            'description_fa': 'مستقیماً به مرکز اعلان‌ها بروید.',
            'url': f"{reverse('home')}#notifications",
        },
    ]

    recent_projects = Project.objects.order_by('-start_date')[:6]
    recent_logs = ActivityLog.objects.select_related('user').all()[:10]
    unread_notifications = (
        Notification.objects.select_related('recipient')
        .filter(is_read=False)
        .order_by('-created_at')[:10]
    )
    panel_overview: List[Dict[str, Any]] = []
    for field, label_en, label_fa in MEMBERSHIP_PANEL_DEFINITIONS:
        panel_overview.append(
            {
                'field': field,
                'label_en': label_en,
                'label_fa': label_fa,
                'count': Membership.objects.filter(**{field: True}).count(),
            }
        )

    context = {
        'stats': stats,
        'recent_projects': recent_projects,
        'recent_logs': recent_logs,
        'unread_notifications': unread_notifications,
        'panel_overview': panel_overview,
        'projects_attention': projects_attention,
        'quick_actions': quick_actions,
        'alert_collections': alert_collections,
        'overdue_projects': overdue_projects,
        'projects_starting_soon': starting_soon_projects,
    }
    return render(request, 'superadmin_dashboard.html', context)


def _user_is_organisation(user: User) -> bool:
    if getattr(user, 'is_superuser', False):
        return True
    profile = getattr(user, 'profile', None)
    return bool(profile and profile.organization)


def _localise_text(lang: str, english: str, persian: str) -> str:
    """Return the appropriate string for the provided language code."""

    return persian if lang == 'fa' else english


def _get_lang(request: HttpRequest) -> str:
    """Return the preferred language code stored on the session."""

    return request.session.get('lang', 'en')


def _build_breadcrumbs(lang: str, *segments: Tuple[str, Optional[str]]) -> List[Dict[str, str]]:
    """Construct a breadcrumb trail starting from the dashboard home page."""

    breadcrumbs: List[Dict[str, str]] = [
        {'label': _localise_text(lang, 'Home', 'خانه'), 'url': reverse('home')}
    ]
    for label, url in segments:
        breadcrumbs.append({'label': label, 'url': url or ''})
    return breadcrumbs


def _project_deadline_locked_for_user(project: Project, user: User) -> bool:
    """Return True when the project's deadline has passed for this user."""

    if getattr(user, 'is_superuser', False):
        return False
    today = timezone.now().date()
    if today <= project.deadline:
        return False
    ensure_project_deadline_notifications(project)
    return not Membership.objects.filter(project=project, user=user, is_owner=True).exists()


def _user_has_panel(user: User, panel: str) -> bool:
    """Check whether the user has access to a panel respecting deadlines."""

    if getattr(user, 'is_superuser', False):
        return True
    memberships = Membership.objects.filter(user=user)
    if not memberships.exists() and _user_is_organisation(user):
        return True
    panel_filter = {panel: True}
    return memberships.filter(**panel_filter).exists()


def _ensure_project_deadline_access(request: HttpRequest, project: Project) -> bool:
    """Ensure the current user may access the project after its deadline."""

    if getattr(request.user, 'is_superuser', False):
        return True
    if not _project_deadline_locked_for_user(project, request.user):
        return True
    messages.error(
        request,
        f'Access denied: "{project.name}" is locked because the deadline has passed. Only the owner may use this panel.',
    )
    return False


def _get_locked_projects(user: User, panel: str | None = None) -> List[Project]:
    """Return projects that are locked for the user because the deadline passed."""

    today = timezone.now().date()
    memberships = Membership.objects.filter(
        user=user,
        project__deadline__lt=today,
        is_owner=False,
    )
    if panel:
        memberships = memberships.filter(**{panel: True})
    projects = {m.project for m in memberships.select_related('project')}
    return list(projects)


# Helper function to log user actions
def log_activity(user: User, action: str, details: str = '') -> None:
    """Create a log entry recording the specified action.

    Args:
        user: The user who performed the action.  May be None if the
            action occurred anonymously.
        action: A short description of the action (e.g., "Saved quotas").
        details: Optional additional information about the action.
    """
    try:
        ActivityLog.objects.create(user=user, action=action, details=details)
    except Exception:
        # In case logging fails (e.g. during migrations) do not disrupt the main flow
        pass


def _sanitize_identifier(name: str) -> str:
    """Sanitise a string into a valid PostgreSQL identifier.

    Removes invalid characters, replaces non‑alphanumeric characters with
    underscores and truncates to 63 characters to comply with PostgreSQL's
    identifier length limit.  If the identifier begins with a digit it is
    prefixed with ``c_`` to ensure it starts with an alphabetic character.

    Args:
        name: The raw name to sanitise.

    Returns:
        A lowercase identifier safe for use in SQL identifiers.
    """
    cleaned = re.sub(r'[^A-Za-z0-9_]+', '_', str(name)).lower()
    if cleaned and cleaned[0].isdigit():
        cleaned = f"c_{cleaned}"
    return cleaned[:63]


def _normalise_record_value(value: Any) -> str:
    """Render record values as strings for filtering and display."""

    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    if value is None:
        return ''
    return str(value)


def _coerce_numeric(value: str) -> Optional[float]:
    """Attempt to coerce a string value to a float, handling localised digits."""

    normalised = value.strip()
    if not normalised:
        return None
    translate_table = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
    normalised = normalised.translate(translate_table)
    normalised = normalised.replace('٬', '').replace(',', '').replace('٫', '.').replace('%', '')
    try:
        return float(normalised)
    except ValueError:
        return None


def _matches_filter_value(cell_text: str, filter_text: str) -> bool:
    """Evaluate whether a table cell matches the provided filter string."""

    if not filter_text:
        return True
    candidate = filter_text.strip()
    if not candidate:
        return True
    range_match = re.match(r'^\s*(-?\d+(?:[.,]\d+)?)\s*[-–]\s*(-?\d+(?:[.,]\d+)?)\s*$', candidate)
    cell_number = _coerce_numeric(cell_text)
    if range_match and cell_number is not None:
        min_val = _coerce_numeric(range_match.group(1))
        max_val = _coerce_numeric(range_match.group(2))
        if min_val is None or max_val is None:
            return False
        low, high = sorted((min_val, max_val))
        return low <= cell_number <= high
    comparator_match = re.match(r'^\s*(<=|>=|<|>|=)\s*(-?\d+(?:[.,]\d+)?)\s*$', candidate)
    if comparator_match and cell_number is not None:
        comparator = comparator_match.group(1)
        compare_value = _coerce_numeric(comparator_match.group(2))
        if compare_value is None:
            return False
        if comparator == '<':
            return cell_number < compare_value
        if comparator == '<=':
            return cell_number <= compare_value
        if comparator == '>':
            return cell_number > compare_value
        if comparator == '>=':
            return cell_number >= compare_value
        return cell_number == compare_value
    direct_number = _coerce_numeric(candidate)
    if direct_number is not None and cell_number is not None:
        return cell_number == direct_number
    return candidate.lower() in cell_text.lower()


def _extract_submission_id(record: Dict[str, Any]) -> str:
    """Return the best identifier for a record."""

    for key in ('_id', '_uuid', 'uuid'):
        value = record.get(key)
        if value is not None:
            return str(value)
    return ''


def _detect_sort_type(records: Iterable[Dict[str, Any]], column: str) -> str:
    """Guess the sort type for a given column."""

    for record in records:
        value = record.get(column)
        if isinstance(value, (int, float)):
            return 'numeric'
        if isinstance(value, str) and _coerce_numeric(value) is not None:
            return 'numeric'
    return 'text'


################################################################################
# Table export helpers
################################################################################

def _normalise_table_value(value: Any) -> str:
    return _normalise_record_value(value)


def _evaluate_text_condition(cell_text: str, operator: str, values: List[str]) -> bool:
    candidate = cell_text.lower()
    first = (values[0] if values else '') or ''
    query = first.lower()
    if operator == 'eq':
        return candidate == query
    if operator == 'neq':
        return candidate != query
    if operator == 'notContains':
        return query not in candidate
    if operator == 'startsWith':
        return candidate.startswith(query)
    if operator == 'endsWith':
        return candidate.endswith(query)
    if operator == 'empty':
        return candidate == ''
    if operator == 'notEmpty':
        return candidate != ''
    return query in candidate


def _evaluate_number_condition(cell_text: str, operator: str, values: List[str]) -> bool:
    number = _coerce_numeric(cell_text)
    if operator == 'empty':
        return number is None
    if operator == 'notEmpty':
        return number is not None
    first_value = _coerce_numeric(values[0]) if values else None
    second_value = _coerce_numeric(values[1]) if len(values) > 1 else None
    if operator == 'between' and first_value is not None and second_value is not None:
        if number is None:
            return False
        low, high = sorted((first_value, second_value))
        return low <= number <= high
    if number is None or first_value is None:
        return False
    if operator == 'gt':
        return number > first_value
    if operator == 'gte':
        return number >= first_value
    if operator == 'lt':
        return number < first_value
    if operator == 'lte':
        return number <= first_value
    if operator == 'neq':
        return number != first_value
    return number == first_value


def _evaluate_advanced_condition(
    row: Dict[str, Any],
    column_meta: Dict[str, Any],
    condition: Dict[str, Any],
) -> bool:
    field = column_meta.get('field')
    if not field:
        return False
    operator = condition.get('operator') or 'contains'
    cell_text = _normalise_table_value(row.get(field, ''))
    cond_type = condition.get('type') or column_meta.get('type') or 'text'
    values = condition.get('values') if isinstance(condition.get('values'), list) else []
    if operator == 'empty':
        return cell_text == ''
    if operator == 'notEmpty':
        return cell_text != ''
    if cond_type == 'number':
        return _evaluate_number_condition(cell_text, operator, values)
    return _evaluate_text_condition(cell_text, operator, values)


def _evaluate_advanced_filters(
    row: Dict[str, Any],
    column_map: Dict[int, Dict[str, Any]],
    advanced_spec: Dict[str, Any],
) -> bool:
    filters = advanced_spec.get('filters')
    if not isinstance(filters, list) or not filters:
        return True
    results: List[bool] = []
    for condition in filters:
        try:
            column_index = int(condition.get('column'))
        except (TypeError, ValueError):
            results.append(False)
            continue
        column_meta = column_map.get(column_index)
        if not column_meta:
            results.append(False)
            continue
        results.append(_evaluate_advanced_condition(row, column_meta, condition))
    logic = advanced_spec.get('logic')
    if logic == 'or':
        return any(results)
    return all(results)


def _filter_table_rows(
    rows: List[Dict[str, Any]],
    columns: List[Dict[str, Any]],
    filters: Dict[str, Any],
) -> List[Dict[str, Any]]:
    if not rows or not filters:
        return rows
    column_map: Dict[int, Dict[str, Any]] = {
        index: column for index, column in enumerate(columns)
    }
    global_term = str(filters.get('global') or '').strip().lower()
    column_filters = filters.get('columnFilters') if isinstance(filters.get('columnFilters'), list) else []
    advanced_spec = filters.get('advanced') if isinstance(filters.get('advanced'), dict) else {}
    filtered: List[Dict[str, Any]] = []
    for row in rows:
        if global_term:
            found = False
            for column in column_map.values():
                field = column.get('field')
                if not field:
                    continue
                if global_term in _normalise_table_value(row.get(field, '')).lower():
                    found = True
                    break
            if not found:
                continue
        matches_basic = True
        for filter_spec in column_filters:
            try:
                column_index = int(filter_spec.get('column'))
            except (TypeError, ValueError):
                continue
            column_meta = column_map.get(column_index)
            if not column_meta or not column_meta.get('field'):
                continue
            value_text = _normalise_table_value(row.get(column_meta['field'], ''))
            if filter_spec.get('type') == 'number':
                if not _matches_filter_value(value_text, filter_spec.get('value', '')):
                    matches_basic = False
                    break
            else:
                candidate = (filter_spec.get('valueLower') or filter_spec.get('value') or '').strip().lower()
                if candidate and candidate not in value_text.lower():
                    matches_basic = False
                    break
        if not matches_basic:
            continue
        if advanced_spec and not _evaluate_advanced_filters(row, column_map, advanced_spec):
            continue
        filtered.append(row)
    sort_spec = filters.get('sort') if isinstance(filters.get('sort'), dict) else None
    if sort_spec and sort_spec.get('column') is not None:
        return _sort_filtered_rows(filtered, column_map, sort_spec)
    return filtered


def _sort_filtered_rows(
    rows: List[Dict[str, Any]],
    column_map: Dict[int, Dict[str, Any]],
    sort_spec: Dict[str, Any],
) -> List[Dict[str, Any]]:
    try:
        column_index = int(sort_spec.get('column'))
    except (TypeError, ValueError):
        return rows
    column_meta = column_map.get(column_index)
    if not column_meta or not column_meta.get('field'):
        return rows
    direction = -1 if sort_spec.get('direction') == 'desc' else 1
    field = column_meta['field']

    def comparator(left: Tuple[int, Dict[str, Any]], right: Tuple[int, Dict[str, Any]]) -> int:
        idx_a, row_a = left
        idx_b, row_b = right
        value_a = _normalise_table_value(row_a.get(field, ''))
        value_b = _normalise_table_value(row_b.get(field, ''))
        if column_meta.get('type') == 'number':
            num_a = _coerce_numeric(value_a)
            num_b = _coerce_numeric(value_b)
            if num_a is None and num_b is None:
                return idx_a - idx_b
            if num_a is None:
                return 1 * direction
            if num_b is None:
                return -1 * direction
            if num_a == num_b:
                return idx_a - idx_b
            return direction if num_a > num_b else -direction
        text_a = value_a.lower()
        text_b = value_b.lower()
        if text_a == text_b:
            return idx_a - idx_b
        return direction if text_a > text_b else -direction

    decorated = list(enumerate(rows))
    decorated.sort(key=cmp_to_key(comparator))
    return [row for _, row in decorated]


def _format_membership_panels(membership: Membership) -> str:
    labels: List[str] = []
    for field in MEMBERSHIP_PANEL_FIELDS:
        if getattr(membership, field, False):
            label = MEMBERSHIP_PANEL_LABELS.get(field)
            if label:
                labels.append(label)
    return ', '.join(labels)


def _build_membership_export_dataset(request: HttpRequest, params: Dict[str, Any]) -> Dict[str, Any]:
    lang = request.session.get('lang', 'en')
    user = request.user
    lang = _get_lang(request)
    lang = request.session.get('lang', 'en')
    if not _user_is_organisation(user):
        raise PermissionError(_localise_text(lang, 'Access denied.', 'دسترسی مجاز نیست.'))
    projects = _get_accessible_projects(user)
    if not projects:
        raise PermissionError(
            _localise_text(lang, 'No projects available for export.', 'پروژه‌ای برای خروجی در دسترس نیست.')
        )
    memberships = (
        Membership.objects.filter(project__in=projects)
        .select_related('user__profile', 'project')
        .order_by('project__name', 'user__username')
    )
    columns = [
        {'field': '__selection__', 'label': 'Select', 'type': 'text', 'export': False},
        {'field': 'email', 'label': 'Email', 'type': 'text', 'export': True},
        {'field': 'full_name', 'label': 'Full Name', 'type': 'text', 'export': True},
        {'field': 'phone', 'label': 'Phone', 'type': 'text', 'export': True},
        {'field': 'project', 'label': 'Project', 'type': 'text', 'export': True},
        {'field': 'start_work', 'label': 'Start Work', 'type': 'text', 'export': True},
        {'field': 'owner', 'label': 'Owner', 'type': 'text', 'export': True},
        {'field': 'panels', 'label': 'Panels', 'type': 'text', 'export': True},
        {'field': '__actions__', 'label': 'Actions', 'type': 'text', 'export': False},
    ]
    owner_label = _localise_text(lang, 'Owner', 'مالک')
    member_label = _localise_text(lang, 'Member', 'عضو')
    rows: List[Dict[str, Any]] = []
    for membership in memberships:
        user_obj = membership.user
        full_name = user_obj.get_full_name().strip() if user_obj.get_full_name() else user_obj.first_name
        profile = getattr(user_obj, 'profile', None)
        rows.append(
            {
                '__selection__': '',
                'email': user_obj.username,
                'full_name': full_name or user_obj.username,
                'phone': getattr(profile, 'phone', ''),
                'project': membership.project.name,
                'start_work': membership.start_work,
                'owner': owner_label if membership.is_owner else member_label,
                'panels': _format_membership_panels(membership) or '-',
                '__actions__': '',
            }
        )
    return {'columns': columns, 'rows': rows, 'filename': 'memberships'}


def _build_projects_export_dataset(request: HttpRequest, params: Dict[str, Any]) -> Dict[str, Any]:
    lang = request.session.get('lang', 'en')
    user = request.user
    if not _user_is_organisation(user):
        raise PermissionError(_localise_text(lang, 'Access denied.', 'دسترسی مجاز نیست.'))
    projects = _get_accessible_projects(user)
    columns = [
        {'field': 'name', 'label': 'Name', 'type': 'text', 'export': True},
        {'field': 'status', 'label': 'Status', 'type': 'text', 'export': True},
        {'field': 'type', 'label': 'Type', 'type': 'text', 'export': True},
        {'field': 'start_date', 'label': 'Start Date', 'type': 'text', 'export': True},
        {'field': 'deadline', 'label': 'Deadline', 'type': 'text', 'export': True},
        {'field': 'sample_size', 'label': 'Sample Size', 'type': 'number', 'export': True},
        {'field': 'filled_samples', 'label': 'Filled Samples', 'type': 'number', 'export': True},
        {'field': '__actions__', 'label': 'Actions', 'type': 'text', 'export': False},
    ]
    rows = []
    for project in projects:
        rows.append(
            {
                'name': project.name,
                'status': _localise_text(lang, 'Active', 'فعال') if project.status else _localise_text(lang, 'Inactive', 'غیرفعال'),
                'type': project.type,
                'start_date': project.start_date,
                'deadline': project.deadline,
                'sample_size': project.sample_size,
                'filled_samples': project.filled_samples,
                '__actions__': '',
            }
        )
    return {'columns': columns, 'rows': rows, 'filename': 'projects'}


def _build_database_export_dataset(request: HttpRequest, params: Dict[str, Any]) -> Dict[str, Any]:
    lang = request.session.get('lang', 'en')
    user = request.user
    lang = _get_lang(request)
    if not _user_has_panel(user, 'database_management'):
        raise PermissionError(_localise_text(lang, 'Access denied.', 'دسترسی مجاز نیست.'))
    projects = _get_accessible_projects(user, panel='database_management')
    entries = DatabaseEntry.objects.filter(project__in=projects).select_related('project')
    columns = [
        {'field': 'project', 'label': 'Project', 'type': 'text', 'export': True},
        {'field': 'db_name', 'label': 'DB Name', 'type': 'text', 'export': True},
        {'field': 'token', 'label': 'Token', 'type': 'text', 'export': True},
        {'field': 'asset_id', 'label': 'Asset ID', 'type': 'text', 'export': True},
        {'field': 'status', 'label': 'Status', 'type': 'text', 'export': True},
        {'field': '__actions__', 'label': 'Actions', 'type': 'text', 'export': False},
    ]
    rows = []
    for entry in entries:
        status_label = _localise_text(lang, 'Synced', 'همگام شده') if entry.status else _localise_text(lang, 'Pending', 'در انتظار')
        rows.append(
            {
                'project': entry.project.name,
                'db_name': entry.db_name,
                'token': entry.token,
                'asset_id': entry.asset_id,
                'status': status_label,
                '__actions__': '',
            }
        )
    return {'columns': columns, 'rows': rows, 'filename': 'databases'}


def _build_activity_export_dataset(request: HttpRequest, params: Dict[str, Any]) -> Dict[str, Any]:
    lang = request.session.get('lang', 'en')
    if not _user_is_organisation(request.user):
        raise PermissionError(_localise_text(lang, 'Access denied.', 'دسترسی مجاز نیست.'))
    logs = ActivityLog.objects.select_related('user').all()[:500]
    columns = [
        {'field': 'timestamp', 'label': 'Timestamp', 'type': 'text', 'export': True},
        {'field': 'user', 'label': 'User', 'type': 'text', 'export': True},
        {'field': 'action', 'label': 'Action', 'type': 'text', 'export': True},
        {'field': 'details', 'label': 'Details', 'type': 'text', 'export': True},
    ]
    rows = []
    for log in logs:
        rows.append(
            {
                'timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                'user': log.user.username if log.user else '—',
                'action': log.action,
                'details': log.details,
            }
        )
    return {'columns': columns, 'rows': rows, 'filename': 'activity-logs'}


def _resolve_entry_param(params: Dict[str, Any], key_variants: Iterable[str]) -> int:
    for key in key_variants:
        value = params.get(key)
        if value in (None, '', 'null'):
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            raise ValueError('Invalid entry identifier provided.')
    raise ValueError('A database entry identifier is required for export.')


def _resolve_project_param(params: Dict[str, Any], key_variants: Iterable[str]) -> int:
    for key in key_variants:
        value = params.get(key)
        if value in (None, '', 'null'):
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            raise ValueError('Invalid project identifier provided.')
    raise ValueError('A project identifier is required for export.')


def _extract_param_values(raw: Any) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, (list, tuple, set)):
        values: List[str] = []
        for item in raw:
            values.extend(_extract_param_values(item))
        return values
    return [str(raw)]


def _parse_int_param_list(raw: Any) -> List[int]:
    values: List[int] = []
    for chunk in _extract_param_values(raw):
        parts = [part.strip() for part in chunk.split(',')]
        for part in parts:
            if not part:
                continue
            try:
                number = int(part)
            except (TypeError, ValueError):
                continue
            if number not in values:
                values.append(number)
    return values


def _parse_iso_datetime_param(raw: Any) -> Optional[datetime]:
    if raw in (None, '', 'null'):
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        candidate = datetime.fromisoformat(text)
    except ValueError:
        return None
    if timezone.is_naive(candidate):
        candidate = timezone.make_aware(candidate, timezone.get_current_timezone())
    return candidate


def _build_database_view_export_dataset(request: HttpRequest, params: Dict[str, Any]) -> Dict[str, Any]:
    lang = request.session.get('lang', 'en')
    user = request.user
    lang = _get_lang(request)
    if not _user_has_panel(user, 'database_management'):
        raise PermissionError(_localise_text(lang, 'Access denied.', 'دسترسی مجاز نیست.'))
    entry_id = _resolve_entry_param(params, ('entry', 'entryId'))
    entry = get_object_or_404(DatabaseEntry, pk=entry_id)
    projects = _get_accessible_projects(user, panel='database_management')
    if entry.project not in projects or _project_deadline_locked_for_user(entry.project, user):
        raise PermissionError(_localise_text(lang, 'Access denied.', 'دسترسی مجاز نیست.'))
    snapshot = load_entry_snapshot(entry)
    records = snapshot.records
    columns = [
        {'field': column, 'label': column, 'type': 'text', 'export': True}
        for column in infer_columns(records)
    ]
    rows = []
    for record in records:
        rows.append({column['field']: record.get(column['field'], '') for column in columns})
    filename = _sanitize_identifier(entry.db_name or 'database')
    return {'columns': columns, 'rows': rows, 'filename': filename or 'database'}


def _build_qc_export_dataset(request: HttpRequest, params: Dict[str, Any]) -> Dict[str, Any]:
    lang = request.session.get('lang', 'en')
    user = request.user
    if not (
        _user_has_panel(user, 'qc_management')
        or _user_has_panel(user, 'qc_performance')
        or _user_has_panel(user, 'edit_data')
    ):
        raise PermissionError(_localise_text(lang, 'Access denied.', 'دسترسی مجاز نیست.'))
    entry_id = _resolve_entry_param(params, ('entry', 'entryId'))
    entry = get_object_or_404(DatabaseEntry, pk=entry_id)
    if _project_deadline_locked_for_user(entry.project, user):
        raise PermissionError(_localise_text(lang, 'Access denied.', 'دسترسی مجاز نیست.'))
    snapshot = load_entry_snapshot(entry)
    records = snapshot.records
    column_names = infer_columns(records)
    columns = [
        {'field': column, 'label': column, 'type': 'text', 'export': True}
        for column in column_names
    ]
    rows = []
    for record in records:
        rows.append({column: _normalise_record_value(record.get(column, '')) for column in column_names})
    filename = f"qc-entry-{entry.pk}"
    return {'columns': columns, 'rows': rows, 'filename': filename}


def _default_qc_measure(lang: str) -> List[Dict[str, Any]]:
    """Return a single default QC measure node labeled for the current language."""

    label = _localise_text(lang, 'Sample', 'نمونه')
    return [
        {
            'id': 'qc-sample',
            'label': label,
            'field': 'sample',
            'children': [],
        }
    ]


def _flatten_measure_leaves(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return a flat list of measurement leaves preserving order."""

    leaves: List[Dict[str, Any]] = []

    def walk(node: Dict[str, Any]) -> None:
        children = node.get('children') or []
        if children:
            for child in children:
                walk(child)
            return
        leaves.append(
            {
                'id': str(node.get('id') or ''),
                'label': str(node.get('label') or node.get('field') or ''),
                'field': str(node.get('field') or node.get('label') or ''),
            }
        )

    for node in nodes:
        walk(node)
    return leaves


def _boolean_display(value: Any, lang: str) -> str:
    """Return a normalised True/False label for assignment cells."""

    truthy = {'true', '1', 'yes', 'y', 't', 'on', 'checked', '✓', '✔'}
    falsy = {'false', '0', 'no', 'n', 'f', 'off', '✕', '×'}

    if isinstance(value, bool):
        is_true = value
        is_false = not value
    else:
        text = str(value or '').strip().casefold()
        if not text:
            return ''
        is_true = text in truthy
        is_false = text in falsy

    if is_true:
        return _localise_text(lang, 'True', 'صحیح')
    if is_false:
        return _localise_text(lang, 'False', 'غلط')
    return str(value or '')


def _load_qc_measure_structure(
    request: HttpRequest, entry: DatabaseEntry | None, columns: List[str], lang: str
) -> List[Dict[str, Any]]:
    """Load the saved QC measure structure for an entry or return a default tree."""

    stored = None
    if entry:
        stored = (request.session.get('qc_measure') or {}).get(str(entry.pk))
    if stored:
        return stored
    return _default_qc_measure(lang)


@login_required
def qc_management_view(request: HttpRequest) -> HttpResponse:
    """Interactive workspace for QC measure design and assignments."""

    user = request.user
    lang = request.session.get('lang', 'en')
    if not _user_has_panel(user, 'qc_management'):
        messages.error(request, _localise_text(lang, 'Access denied.', 'دسترسی مجاز نیست.'))
        return redirect('home')

    project_qs = Project.objects.all()
    if not (_user_is_organisation(user) or getattr(user, 'is_superuser', False)):
        project_qs = project_qs.filter(memberships__user=user, memberships__qc_management=True)
    projects = list(project_qs.distinct().order_by('name'))

    selected_project: Optional[Project] = None
    selected_entry: Optional[DatabaseEntry] = None
    entries: List[DatabaseEntry] = []
    assignment_rows: List[Dict[str, Any]] = []
    assignment_filters: List[Dict[str, Any]] = []
    assignment_columns: List[Dict[str, Any]] = []
    qc_measure_tree: List[Dict[str, Any]] = []
    default_qc_measure = _default_qc_measure(lang)
    measure_saved = False
    measure_leaves: List[Dict[str, Any]] = []
    entry_columns: List[str] = []
    snapshot = None
    total_records = 0
    total_pages = 1
    page = 1
    page_size = 5
    min_page_size = 1
    max_page_size = 500
    page_sizes = [5, 25, 50, 100]
    start_index = 0
    end_index = 0
    has_previous = False
    has_next = False
    phone_num = (request.GET.get('phone_num') or '').strip()

    project_param = request.GET.get('project')
    if project_param:
        for project in projects:
            if str(project.pk) == project_param:
                selected_project = project
                break

    if selected_project:
        entries = list(DatabaseEntry.objects.filter(project=selected_project).order_by('db_name'))
        entry_param = request.GET.get('entry')
        if entry_param:
            for entry in entries:
                if str(entry.pk) == entry_param:
                    selected_entry = entry
                    break

    if selected_entry:
        snapshot = load_entry_snapshot(selected_entry)
        columns = infer_columns(snapshot.records)
        entry_columns = columns
        stored_measure = (request.session.get('qc_measure') or {}).get(
            str(selected_entry.pk)
        )
        if phone_num and phone_num not in columns:
            phone_num = ''
        qc_measure_tree = stored_measure or default_qc_measure
        measure_saved = stored_measure is not None
        measure_leaves = _flatten_measure_leaves(qc_measure_tree)
        if not measure_leaves:
            measure_leaves = _flatten_measure_leaves(default_qc_measure)

        for idx, column in enumerate(entry_columns):
            filter_val = (request.GET.get(f'filter_{idx}') or '').strip()
            assignment_filters.append(
                {
                    'index': idx,
                    'label': column,
                    'value': filter_val,
                    'field': column,
                    'filter_name': f'filter_{idx}',
                }
            )

        column_filters = {
            column: filt['value']
            for column, filt in zip(entry_columns, assignment_filters)
            if filt['value']
        }

        db_rows: List[Dict[str, Any]] = []
        db_phone_index: Dict[str, List[Dict[str, Any]]] = {}

        for idx, record in enumerate(snapshot.records):
            submission_id = _extract_submission_id(record) or f"row-{idx}"
            phone_value = _normalise_record_value(record.get(phone_num, '')).strip() if phone_num else ''
            payload = {
                'record': record,
                'submission_id': submission_id,
                'phone_value': phone_value,
            }
            db_rows.append(payload)
            db_phone_index.setdefault(phone_value, []).append(payload)

        interview_rows: List[Dict[str, Any]] = []
        interview_queryset = (
            Interview.objects.filter(project=selected_project)
            .select_related('person')
            .prefetch_related('person__mobiles')
            if phone_num
            else []
        )

        for interview in interview_queryset:
            mobiles = []
            if hasattr(interview, 'mobile'):
                mobile_value = getattr(interview, 'mobile')
                if mobile_value is not None:
                    mobiles.append(str(mobile_value))
            if not mobiles and interview.person:
                mobiles.extend(list(interview.person.mobiles.values_list('mobile', flat=True)))
            if not mobiles:
                mobiles.append('')

            for mobile_value in mobiles:
                normalized_mobile = _normalise_record_value(mobile_value).strip()
                interview_rows.append(
                    {
                        'interview': interview,
                        'mobile': normalized_mobile,
                        'submission_id': f"interview-{interview.id}",
                    }
                )

        joined_rows: List[Dict[str, Any]] = []

        if phone_num:
            matched_db_records: set[str] = set()

            for interview_data in interview_rows:
                mobile_value = interview_data['mobile']
                matched_records = db_phone_index.get(mobile_value)

                if matched_records:
                    for record in matched_records:
                        matched_db_records.add(record['submission_id'])
                        joined_rows.append(
                            {
                                'record': record['record'],
                                'interview': interview_data['interview'],
                                'phone_value': mobile_value,
                                'submission_id': record['submission_id'],
                            }
                        )
                else:
                    joined_rows.append(
                        {
                            'record': {},
                            'interview': interview_data['interview'],
                            'phone_value': mobile_value,
                            'submission_id': f"{interview_data['submission_id']}-{mobile_value or 'nomobile'}",
                        }
                    )

            for record in db_rows:
                if record['submission_id'] in matched_db_records:
                    continue
                joined_rows.append(
                    {
                        'record': record['record'],
                        'interview': None,
                        'phone_value': record['phone_value'],
                        'submission_id': record['submission_id'],
                    }
                )
        else:
            joined_rows = [
                {
                    'record': record['record'],
                    'interview': None,
                    'phone_value': record['phone_value'],
                    'submission_id': record['submission_id'],
                }
                for record in db_rows
            ]

        filtered_records: List[Tuple[Dict[str, Any], Dict[str, str]]] = []
        for row in joined_rows:
            record_data = row.get('record') or {}
            value_map: Dict[str, str] = {}
            for column in entry_columns:
                raw_value = record_data.get(column, '')
                value_map[column] = _normalise_record_value(raw_value)
            matches = True
            for col, filter_text in column_filters.items():
                if not _matches_filter_value(value_map.get(col, ''), filter_text):
                    matches = False
                    break
            if matches:
                filtered_records.append((row, value_map))

        total_records = len(filtered_records)
        try:
            requested_size = int(request.GET.get('page_size', page_size))
        except (TypeError, ValueError):
            requested_size = page_size
        page_size = min(max(requested_size, min_page_size), max_page_size)
        total_pages = max(1, ceil(total_records / page_size))
        try:
            requested_page = int(request.GET.get('page', 1))
        except (TypeError, ValueError):
            requested_page = 1
        page = min(max(1, requested_page), total_pages)
        start_index = (page - 1) * page_size
        end_index = min(start_index + page_size, total_records)
        has_previous = page > 1
        has_next = page < total_pages
        page_slice = filtered_records[start_index:end_index]

        assignment_columns = [
            {'name': 'Select', 'sort_type': 'text', 'is_select': True},
        ]
        assignment_columns.extend(
            [
                {
                    'name': leaf['label'],
                    'sort_type': 'text',
                    'field': leaf['field'],
                    'is_measure': True,
                }
                for leaf in measure_leaves
            ]
        )
        assignment_columns.extend(
            [
                {
                    'name': column,
                    'sort_type': _detect_sort_type(snapshot.records, column),
                    'field': column,
                    'filterable': True,
                    'filter_name': f'filter_{idx}',
                    'filter_value': assignment_filters[idx]['value'],
                    'filter_label': column,
                }
                for idx, column in enumerate(entry_columns)
            ]
        )

        for record, value_map in page_slice:
            submission_id = record.get('submission_id', '') or ''
            measure_values = [
                _boolean_display(value_map.get(leaf['field'], ''), lang)
                for leaf in measure_leaves
            ]
            rows = [value_map.get(column, '') for column in entry_columns]
            assignment_rows.append({
                'id': submission_id,
                'measure_values': measure_values,
                'values': rows,
            })

    context = {
        'projects': projects,
        'selected_project': selected_project,
        'entries': entries,
        'selected_entry': selected_entry,
        'qc_measure_tree': qc_measure_tree,
        'measure_leaves': measure_leaves,
        'entry_columns': entry_columns,
        'phone_num': phone_num,
        'assignment_columns': assignment_columns,
        'assignment_rows': assignment_rows,
        'assignment_filters': assignment_filters,
        'page': page,
        'page_size': page_size,
        'page_sizes': page_sizes,
        'min_page_size': min_page_size,
        'max_page_size': max_page_size,
        'total_pages': total_pages,
        'total_records': total_records,
        'start_index': start_index + 1 if total_records else 0,
        'end_index': end_index,
        'has_previous': has_previous,
        'has_next': has_next,
        'default_qc_measure': default_qc_measure,
        'measure_saved': measure_saved,
        'qc_assignment_endpoint': reverse('qc_assignment_assign'),
        'lang': lang,
        'breadcrumbs': _build_breadcrumbs(
            lang,
            (_localise_text(lang, 'Quality Control', 'کنترل کیفیت'), ''),
            (_localise_text(lang, 'QC Management', 'مدیریت QC'), ''),
        ),
    }
    return render(request, 'qc_management.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def qc_management_config(request: HttpRequest) -> JsonResponse:
    """Return or persist QC measure configuration for a database entry."""

    user = request.user
    lang = request.session.get('lang', 'en')
    if not _user_has_panel(user, 'qc_management'):
        return JsonResponse({'error': _localise_text(lang, 'Access denied.', 'دسترسی مجاز نیست.')}, status=403)

    try:
        entry_id = int(request.GET.get('entry') or request.POST.get('entry') or 0)
    except (TypeError, ValueError):
        entry_id = 0
    entry = get_object_or_404(DatabaseEntry, pk=entry_id)

    if not (_user_is_organisation(user) or getattr(user, 'is_superuser', False)):
        if not Membership.objects.filter(user=user, project=entry.project, qc_management=True).exists():
            return JsonResponse({'error': _localise_text(lang, 'Access denied.', 'دسترسی مجاز نیست.')}, status=403)

    snapshot = load_entry_snapshot(entry)
    columns = infer_columns(snapshot.records)
    default_measure = _default_qc_measure(lang)
    stored_measure = (request.session.get('qc_measure') or {}).get(str(entry.pk))

    if request.method == 'GET':
        measure = stored_measure or default_measure
        return JsonResponse(
            {
                'measure': measure,
                'default_measure': default_measure,
                'columns': columns,
                'measure_saved': stored_measure is not None,
                'total_records': len(snapshot.records),
            }
        )

    try:
        payload = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': _localise_text(lang, 'Invalid payload.', 'داده ارسالی نامعتبر است.')}, status=400)

    reset_to_default = bool(payload.get('reset_to_default'))
    measure = default_measure if reset_to_default else payload.get('measure')
    if not isinstance(measure, list):
        return JsonResponse({'error': _localise_text(lang, 'Invalid measure structure.', 'ساختار اندازه‌گیری نادرست است.')}, status=400)

    session_store = request.session.get('qc_measure') or {}
    session_store[str(entry.pk)] = measure
    request.session['qc_measure'] = session_store
    request.session.modified = True
    return JsonResponse(
        {
            'ok': True,
            'saved_for': entry.pk,
            'measure': measure,
            'default_measure': default_measure,
            'reset_to_default': reset_to_default,
        }
    )


@login_required
@require_POST
def qc_assignment_assign(request: HttpRequest) -> JsonResponse:
    """Assign QC submission rows to a project member and notify them."""

    lang = request.session.get('lang', 'en')
    user = request.user

    if not _user_has_panel(user, 'qc_management'):
        return JsonResponse({'error': _localise_text(lang, 'Access denied.', 'دسترسی مجاز نیست.')}, status=403)

    try:
        payload = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': _localise_text(lang, 'Invalid payload.', 'داده ارسالی نامعتبر است.')}, status=400)

    try:
        entry_id = int(payload.get('entry') or 0)
    except (TypeError, ValueError):
        entry_id = 0
    email = (payload.get('email') or '').strip()
    submissions_raw = payload.get('submissions')

    if not entry_id:
        return JsonResponse({'error': _localise_text(lang, 'Database entry is required.', 'شناسه پایگاه لازم است.')}, status=400)
    if not email:
        return JsonResponse({'error': _localise_text(lang, 'Email is required.', 'ایمیل الزامی است.')}, status=400)
    if not isinstance(submissions_raw, list):
        return JsonResponse(
            {
                'error': _localise_text(
                    lang,
                    'At least one submission must be selected.',
                    'حداقل یک رکورد باید انتخاب شود.',
                )
            },
            status=400,
        )

    submissions = [str(item).strip() for item in submissions_raw if str(item).strip()]
    if not submissions:
        return JsonResponse(
            {
                'error': _localise_text(
                    lang,
                    'At least one submission must be selected.',
                    'حداقل یک رکورد باید انتخاب شود.',
                )
            },
            status=400,
        )

    entry = get_object_or_404(DatabaseEntry, pk=entry_id)

    if not (_user_is_organisation(user) or getattr(user, 'is_superuser', False)):
        if not Membership.objects.filter(user=user, project=entry.project, qc_management=True).exists():
            return JsonResponse({'error': _localise_text(lang, 'Access denied.', 'دسترسی مجاز نیست.')}, status=403)
        if _project_deadline_locked_for_user(entry.project, user):
            return JsonResponse(
                {
                    'error': _localise_text(
                        lang,
                        'Project deadline has passed. Only the owner may assign.',
                        'ددلاین پروژه گذشته است و تنها مالک می‌تواند تخصیص دهد.',
                    )
                },
                status=403,
            )

    snapshot = load_entry_snapshot(entry)
    entry_columns = infer_columns(snapshot.records)
    available_ids = {_extract_submission_id(record) for record in snapshot.records}
    missing = [sid for sid in submissions if sid not in available_ids]
    if missing:
        return JsonResponse(
            {
                'error': _localise_text(
                    lang,
                    'Some submissions were not found for this entry.',
                    'برخی رکوردهای انتخاب‌شده در این پایگاه یافت نشد.',
                )
            },
            status=404,
        )

    recipient = (
        User.objects.filter(email__iexact=email).first()
        or User.objects.filter(username__iexact=email).first()
    )
    if not recipient:
        return JsonResponse(
            {
                'error': _localise_text(
                    lang,
                    'User not found for the provided email.',
                    'کاربری با این ایمیل یافت نشد.',
                )
            },
            status=404,
        )

    if not Membership.objects.filter(user=recipient, project=entry.project).exists():
        return JsonResponse(
            {
                'error': _localise_text(
                    lang,
                    'Recipient is not a member of this project.',
                    'گیرنده عضو این پروژه نیست.',
                )
            },
            status=400,
        )

    actor_label = user.get_full_name() or user.username
    submission_count = len(submissions)
    measure_definition = _load_qc_measure_structure(request, entry, entry_columns, lang)
    record_map = {_extract_submission_id(record): record for record in snapshot.records}
    with transaction.atomic():
        task = ReviewTask.objects.create(
            entry=entry,
            reviewer=recipient,
            assigned_by=user,
            task_size=submission_count,
            measure_definition=measure_definition,
            columns=entry_columns,
        )
        for submission_id in submissions:
            record = record_map.get(submission_id, {}) or {}
            row_data: Dict[str, Any] = {
                column: record.get(column, '') for column in entry_columns
            }
            review_row = ReviewRow.objects.create(
                task=task,
                submission_id=submission_id,
                data=row_data,
            )
            ReviewAction.objects.create(
                row=review_row,
                action=ReviewAction.Action.ASSIGNED,
                metadata={'assigned_by': actor_label},
            )
    message_en = (
        f'You have {submission_count} QC record(s) assigned for project "{entry.project.name}".'
    )
    message_fa = f'{submission_count} رکورد برای کنترل کیفیت پروژه «{entry.project.name}» به شما ارجاع شد.'

    create_notification(
        recipient,
        message_en=message_en,
        message_fa=message_fa,
        event_type=Notification.EventType.CUSTOM_MESSAGE,
        project=entry.project,
        extra_metadata={
            'entry_id': entry.pk,
            'project_id': entry.project_id,
            'submission_ids': submissions,
            'assigned_by': actor_label,
        },
    )

    ActivityLog.objects.create(
        user=user,
        action='qc_assignment',
        details=json.dumps(
            {
                'entry': entry.pk,
                'project': entry.project_id,
                'assigned_to': recipient.pk,
                'submission_ids': submissions,
            },
            ensure_ascii=False,
        ),
    )

    return JsonResponse({'ok': True, 'assigned_count': submission_count, 'recipient': recipient.pk})


@login_required
def qc_performance_dashboard(request: HttpRequest) -> HttpResponse:
    """Placeholder dashboard for QC performance insights."""

    lang = request.session.get('lang', 'en')
    if not _user_has_panel(request.user, 'qc_performance'):
        messages.error(request, _localise_text(lang, 'Access denied.', 'دسترسی مجاز نیست.'))
        return redirect('home')
    return render(request, 'qc_performance.html', {'lang': lang})


@login_required
def qc_review(request: HttpRequest) -> HttpResponse:
    """Entry point for reviewing submitted data."""

    lang = request.session.get('lang', 'en')
    user = request.user
    if not _user_has_panel(user, 'review_data'):
        messages.error(request, _localise_text(lang, 'Access denied.', 'دسترسی مجاز نیست.'))
        return redirect('home')

    tasks = list(
        ReviewTask.objects.filter(reviewer=user)
        .select_related('entry__project', 'assigned_by')
        .order_by('-created_at')
    )
    task_rows: List[Dict[str, Any]] = []
    for task in tasks:
        remaining = max(task.task_size - task.reviewed_count, 0)
        task_rows.append(
            {
                'id': task.pk,
                'project': task.entry.project,
                'entry': task.entry,
                'task_size': task.task_size,
                'reviewed': task.reviewed_count,
                'remaining': remaining,
                'assigned_by': task.assigned_by,
                'created_at': task.created_at,
                'completed': task.reviewed_count >= task.task_size,
            }
        )

    context = {
        'lang': lang,
        'tasks': task_rows,
        'breadcrumbs': _build_breadcrumbs(
            lang,
            (_localise_text(lang, 'Quality Control', 'کنترل کیفیت'), ''),
            (_localise_text(lang, 'QC Review', 'بازبینی داده'), ''),
        ),
    }
    return render(request, 'qc_review.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def qc_review_detail(request: HttpRequest, task_id: int) -> HttpResponse:
    """Detail view for an individual QC review task."""

    lang = request.session.get('lang', 'en')
    user = request.user
    if not _user_has_panel(user, 'review_data'):
        messages.error(request, _localise_text(lang, 'Access denied.', 'دسترسی مجاز نیست.'))
        return redirect('home')

    task = get_object_or_404(
        ReviewTask.objects.select_related('entry__project', 'assigned_by'),
        pk=task_id,
        reviewer=user,
    )

    snapshot = load_entry_snapshot(task.entry)
    columns = task.columns or infer_columns(snapshot.records)
    measure_definition = task.measure_definition or _load_qc_measure_structure(
        request, task.entry, columns, lang
    )
    measure_leaves = _flatten_measure_leaves(measure_definition)

    rows_qs = task.rows.prefetch_related('checklist_responses')

    def _resolve_row(pk: int) -> ReviewRow:
        return get_object_or_404(rows_qs, pk=pk)

    if request.method == 'POST':
        action = request.POST.get('action')
        try:
            row_id = int(request.POST.get('row_id') or 0)
        except (TypeError, ValueError):
            row_id = 0
        if row_id:
            row = _resolve_row(row_id)
            now = timezone.now()
            if action == 'start':
                if task.started_at is None:
                    task.started_at = now
                    task.save(update_fields=['started_at'])
                if row.started_at is None:
                    row.started_at = now
                    row.save(update_fields=['started_at'])
                ReviewAction.objects.create(row=row, action=ReviewAction.Action.STARTED)
                return redirect(f"{reverse('qc_review_detail', args=[task.pk])}?row={row.pk}")
            if action == 'submit':
                checklist_values: Dict[str, bool] = {}
                for measure in measure_leaves:
                    key = f"measure_{measure['id']}"
                    checklist_values[measure['id']] = request.POST.get(key) is not None
                if task.started_at is None:
                    task.started_at = now
                    task.save(update_fields=['started_at'])
                for measure in measure_leaves:
                    value = checklist_values.get(measure['id'], False)
                    ChecklistResponse.objects.update_or_create(
                        row=row,
                        measure_id=str(measure['id']),
                        defaults={'value': value, 'label': measure.get('label', '')},
                    )
                    row.data[measure.get('field') or measure['id']] = value
                row.started_at = row.started_at or now
                row.completed_at = now
                row.save(update_fields=['data', 'started_at', 'completed_at'])
                ReviewAction.objects.create(
                    row=row,
                    action=ReviewAction.Action.SUBMITTED,
                    metadata={'checklist': checklist_values},
                )
                task.mark_reviewed()
                next_row = (
                    rows_qs.filter(completed_at__isnull=True)
                    .exclude(pk=row.pk)
                    .order_by('created_at')
                    .first()
                )
                if next_row:
                    return redirect(f"{reverse('qc_review_detail', args=[task.pk])}?row={next_row.pk}")
                return redirect('qc_review')

    row_param = request.GET.get('row')
    active_row: Optional[ReviewRow] = None
    if row_param:
        try:
            active_row = _resolve_row(int(row_param))
        except (TypeError, ValueError):
            active_row = None
    if active_row is None:
        active_row = rows_qs.filter(completed_at__isnull=True).order_by('created_at').first()
    if active_row is None:
        active_row = rows_qs.order_by('created_at').first()

    checklist_defaults: Dict[str, bool] = {}
    if active_row:
        checklist_defaults = {
            resp.measure_id: resp.value for resp in active_row.checklist_responses.all()
        }

    rows: List[Dict[str, Any]] = []
    for row in rows_qs:
        value_map: Dict[str, str] = {
            column: _normalise_record_value(row.data.get(column, '')) for column in columns
        }
        checklist_map = {resp.measure_id: resp.value for resp in row.checklist_responses.all()}
        rows.append(
            {
                'obj': row,
                'values': value_map,
                'checklist': checklist_map,
            }
        )

    context = {
        'lang': lang,
        'task': task,
        'rows': rows,
        'columns': columns,
        'measure_leaves': measure_leaves,
        'active_row': active_row,
        'checklist_defaults': checklist_defaults,
        'breadcrumbs': _build_breadcrumbs(
            lang,
            (_localise_text(lang, 'Quality Control', 'کنترل کیفیت'), ''),
            (_localise_text(lang, 'QC Review', 'بازبینی داده'), reverse('qc_review')),
            (_localise_text(lang, 'Task detail', 'جزئیات تسک'), ''),
        ),
    }
    return render(request, 'qc_review_detail.html', context)


@login_required
def product_matrix_ai(request: HttpRequest) -> HttpResponse:
    """Landing page for AI-driven product matrix features."""

    lang = request.session.get('lang', 'en')
    if not _user_has_panel(request.user, 'product_matrix_ai'):
        messages.error(request, _localise_text(lang, 'Access denied.', 'دسترسی مجاز نیست.'))
        return redirect('home')
    return render(request, 'product_matrix_ai.html', {'lang': lang})


def _build_quota_export_dataset(request: HttpRequest, params: Dict[str, Any]) -> Dict[str, Any]:
    lang = request.session.get('lang', 'en')
    user = request.user
    if not _user_has_panel(user, 'quota_management'):
        raise PermissionError(_localise_text(lang, 'Access denied.', 'دسترسی مجاز نیست.'))
    project_id = _resolve_project_param(params, ('project', 'projectId', 'project_id'))
    project = get_object_or_404(Project, pk=project_id)
    accessible = _get_accessible_projects(user, panel='quota_management')
    if project not in accessible or _project_deadline_locked_for_user(project, user):
        raise PermissionError(_localise_text(lang, 'Access denied.', 'دسترسی مجاز نیست.'))
    quotas = list(Quota.objects.filter(project=project))
    city_label = _localise_text(lang, 'City', 'شهر')
    age_label = _localise_text(lang, 'Age Range', 'رنج سنی')
    gender_label = _localise_text(lang, 'Gender', 'جنسیت')
    assigned_label = _localise_text(lang, 'Assigned', 'انجام‌شده')
    target_label = _localise_text(lang, 'Target', 'هدف')
    any_city_label = _localise_text(lang, 'All cities', 'همه شهرها')
    any_age_label = _localise_text(lang, 'All ages', 'تمام سنین')
    any_gender_label = _localise_text(lang, 'Any gender', 'همه جنسیت‌ها')

    columns: List[Dict[str, Any]] = [
        {'field': 'city', 'label': city_label, 'type': 'text', 'export': True},
        {'field': 'age_range', 'label': age_label, 'type': 'text', 'export': True},
        {'field': 'gender', 'label': gender_label, 'type': 'text', 'export': True},
        {'field': 'assigned', 'label': assigned_label, 'type': 'number', 'export': True},
        {'field': 'target', 'label': target_label, 'type': 'number', 'export': True},
    ]
    if not quotas:
        return {'columns': columns, 'rows': [], 'filename': f'quota-{project.pk}'}

    success_counts: Dict[int, int] = defaultdict(int)
    interviews = Interview.objects.filter(project=project, status=True).select_related('person')
    for interview in interviews:
        city_name, age_value, gender_value = _resolve_interview_demographics(interview)
        for quota in quotas:
            if quota.matches(city_name, age_value, gender_value):
                success_counts[quota.pk] += 1
                break

    rows: List[Dict[str, Any]] = []
    for quota in quotas:
        rows.append(
            {
                'city': quota.city or any_city_label,
                'age_range': quota.age_label() if quota.age_start is not None else any_age_label,
                'gender': (_localise_text(lang, 'Male', 'مرد') if quota.gender == 'male' else (
                    _localise_text(lang, 'Female', 'زن') if quota.gender == 'female' else any_gender_label
                )),
                'assigned': success_counts.get(quota.pk, 0),
                'target': quota.target_count,
            }
        )
    return {'columns': columns, 'rows': rows, 'filename': f'quota-{project.pk}'}


def _build_collection_raw_export_dataset(request: HttpRequest, params: Dict[str, Any]) -> Dict[str, Any]:
    lang = request.session.get('lang', 'en')
    user = request.user
    if not _user_has_panel(user, 'collection_performance'):
        raise PermissionError(_localise_text(lang, 'Access denied.', 'دسترسی مجاز نیست.'))
    accessible_projects = _get_accessible_projects(user, panel='collection_performance')
    if not accessible_projects:
        raise ValueError(_localise_text(lang, 'No projects available for export.', 'پروژه‌ای برای خروجی در دسترس نیست.'))
    accessible_ids = {project.pk for project in accessible_projects}
    project_ids = _parse_int_param_list(
        params.get('projects') or params.get('project') or params.get('projectId')
    )
    if project_ids:
        invalid = [pk for pk in project_ids if pk not in accessible_ids]
        if invalid:
            raise PermissionError(_localise_text(lang, 'Access denied.', 'دسترسی مجاز نیست.'))
    else:
        project_ids = list(accessible_ids)
    user_ids = _parse_int_param_list(
        params.get('users') or params.get('user') or params.get('userId')
    )
    start_dt = _parse_iso_datetime_param(params.get('startDate') or params.get('start_date'))
    end_dt = _parse_iso_datetime_param(params.get('endDate') or params.get('end_date'))
    queryset = Interview.objects.select_related('project', 'user').filter(project__in=accessible_projects)
    if project_ids:
        queryset = queryset.filter(project__id__in=project_ids)
    if start_dt:
        queryset = queryset.filter(created_at__gte=start_dt)
    if end_dt:
        queryset = queryset.filter(created_at__lte=end_dt)
    if not _user_is_organisation(user):
        queryset = queryset.filter(user=user)
    elif user_ids:
        queryset = queryset.filter(user__id__in=user_ids)
    queryset = queryset.order_by('-created_at')

    project_label = _localise_text(lang, 'Project', 'پروژه')
    user_label = _localise_text(lang, 'User', 'کاربر')
    code_label = _localise_text(lang, 'Code', 'کد')
    status_label = _localise_text(lang, 'Status', 'وضعیت')
    start_label = _localise_text(lang, 'Form Started', 'شروع فرم')
    end_label = _localise_text(lang, 'Form Submitted', 'پایان فرم')
    created_label = _localise_text(lang, 'Logged', 'زمان ثبت')

    success_text = _localise_text(lang, 'Successful', 'موفق')
    failure_text = _localise_text(lang, 'Unsuccessful', 'ناموفق')
    unknown_text = _localise_text(lang, 'Unknown', 'نامشخص')

    def _format_timestamp(value: Optional[datetime]) -> str:
        if not value:
            return ''
        local_value = timezone.localtime(value)
        return local_value.strftime('%Y-%m-%d %H:%M')

    columns = [
        {'field': 'project', 'label': project_label, 'type': 'text', 'export': True},
        {'field': 'user', 'label': user_label, 'type': 'text', 'export': True},
        {'field': 'code', 'label': code_label, 'type': 'number', 'export': True},
        {'field': 'status', 'label': status_label, 'type': 'text', 'export': True},
        {'field': 'start_form', 'label': start_label, 'type': 'text', 'export': True},
        {'field': 'end_form', 'label': end_label, 'type': 'text', 'export': True},
        {'field': 'created_at', 'label': created_label, 'type': 'text', 'export': True},
    ]
    rows: List[Dict[str, Any]] = []
    for interview in queryset:
        if interview.status is True:
            status_value = success_text
        elif interview.status is False:
            status_value = failure_text
        else:
            status_value = unknown_text
        rows.append(
            {
                'project': interview.project.name if interview.project else '',
                'user': interview.user.first_name or interview.user.get_username(),
                'code': interview.code if interview.code is not None else '',
                'status': status_value,
                'start_form': _format_timestamp(interview.start_form),
                'end_form': _format_timestamp(interview.end_form),
                'created_at': _format_timestamp(interview.created_at),
            }
        )
    return {'columns': columns, 'rows': rows, 'filename': 'collection-raw'}


def _build_collection_top_export_dataset(request: HttpRequest, params: Dict[str, Any]) -> Dict[str, Any]:
    lang = request.session.get('lang', 'en')
    user = request.user
    if not _user_has_panel(user, 'collection_performance'):
        raise PermissionError(_localise_text(lang, 'Access denied.', 'دسترسی مجاز نیست.'))
    accessible_projects = _get_accessible_projects(user, panel='collection_performance')
    if not accessible_projects:
        raise ValueError(_localise_text(lang, 'No projects available for export.', 'پروژه‌ای برای خروجی در دسترس نیست.'))
    accessible_ids = {project.pk for project in accessible_projects}
    project_ids = _parse_int_param_list(
        params.get('projects') or params.get('project') or params.get('projectId')
    )
    if project_ids:
        invalid = [pk for pk in project_ids if pk not in accessible_ids]
        if invalid:
            raise PermissionError(_localise_text(lang, 'Access denied.', 'دسترسی مجاز نیست.'))
    else:
        project_ids = list(accessible_ids)
    user_ids = _parse_int_param_list(
        params.get('users') or params.get('user') or params.get('userId')
    )
    start_dt = _parse_iso_datetime_param(params.get('startDate') or params.get('start_date'))
    end_dt = _parse_iso_datetime_param(params.get('endDate') or params.get('end_date'))
    limit_raw = params.get('limit') or params.get('topLimit')
    try:
        limit = int(limit_raw)
    except (TypeError, ValueError):
        limit = 5
    if limit <= 0:
        limit = 5
    limit = min(limit, 200)
    queryset = Interview.objects.select_related('project', 'user').filter(project__in=accessible_projects)
    if project_ids:
        queryset = queryset.filter(project__id__in=project_ids)
    if start_dt:
        queryset = queryset.filter(created_at__gte=start_dt)
    if end_dt:
        queryset = queryset.filter(created_at__lte=end_dt)
    if not _user_is_organisation(user):
        queryset = queryset.filter(user=user)
    elif user_ids:
        queryset = queryset.filter(user__id__in=user_ids)
    ranking = (
        queryset.values('project__name', 'user__id', 'user__first_name')
        .annotate(total=Count('id'), success=Count('id', filter=Q(status=True)))
        .order_by('-total', 'project__name', 'user__first_name')
    )
    project_label = _localise_text(lang, 'Project', 'پروژه')
    user_label = _localise_text(lang, 'User', 'کاربر')
    total_label = _localise_text(lang, 'Total Calls', 'کل تماس‌ها')
    success_label = _localise_text(lang, 'Successful Calls', 'تماس‌های موفق')
    rate_label = _localise_text(lang, 'Success Rate', 'نرخ موفقیت')
    columns = [
        {'field': 'project', 'label': project_label, 'type': 'text', 'export': True},
        {'field': 'user', 'label': user_label, 'type': 'text', 'export': True},
        {'field': 'total_calls', 'label': total_label, 'type': 'number', 'export': True},
        {'field': 'successful_calls', 'label': success_label, 'type': 'number', 'export': True},
        {'field': 'success_rate', 'label': rate_label, 'type': 'number', 'export': True},
    ]
    rows: List[Dict[str, Any]] = []
    for row in ranking[:limit]:
        total_calls = row['total'] or 0
        successful_calls = row['success'] or 0
        rate = round((successful_calls / total_calls) * 100, 2) if total_calls else 0
        rows.append(
            {
                'project': row['project__name'] or '',
                'user': row['user__first_name'] or str(row['user__id']),
                'total_calls': total_calls,
                'successful_calls': successful_calls,
                'success_rate': rate,
            }
        )
    return {'columns': columns, 'rows': rows, 'filename': 'collection-top'}


TABLE_EXPORT_BUILDERS: Dict[str, Any] = {
    'membership_list': _build_membership_export_dataset,
    'projects_list': _build_projects_export_dataset,
    'database_list': _build_database_export_dataset,
    'activity_logs': _build_activity_export_dataset,
    'database_view': _build_database_view_export_dataset,
    'qc_edit': _build_qc_export_dataset,
    'quota_management': _build_quota_export_dataset,
    'collection_performance_raw': _build_collection_raw_export_dataset,
    'collection_performance_top': _build_collection_top_export_dataset,
}


@login_required
@require_http_methods(["POST"])
def table_export(request: HttpRequest) -> HttpResponse:
    """Return a CSV or Excel export for supported interactive tables."""

    lang = request.session.get('lang', 'en')
    try:
        payload = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        message = _localise_text(lang, 'Invalid export payload.', 'داده ارسال شده نامعتبر است.')
        return JsonResponse({'error': message}, status=400)
    context_name = payload.get('context')
    if not context_name:
        message = _localise_text(lang, 'Table context is required.', 'انتخاب جدول برای خروجی لازم است.')
        return JsonResponse({'error': message}, status=400)
    builder = TABLE_EXPORT_BUILDERS.get(context_name)
    if not builder:
        message = _localise_text(lang, 'This table cannot be exported yet.', 'امکان خروجی گرفتن از این جدول وجود ندارد.')
        return JsonResponse({'error': message}, status=400)
    export_format = (payload.get('format') or 'csv').lower()
    params = payload.get('params') if isinstance(payload.get('params'), dict) else {}
    filters = payload.get('filters') if isinstance(payload.get('filters'), dict) else {}
    try:
        dataset = builder(request, params)
    except PermissionError as exc:
        message = str(exc) or _localise_text(lang, 'Access denied.', 'دسترسی مجاز نیست.')
        return JsonResponse({'error': message}, status=403)
    except (DatabaseCacheError, ValueError) as exc:
        message = str(exc) or _localise_text(lang, 'Unable to prepare export.', 'امکان تهیه خروجی نیست.')
        return JsonResponse({'error': message}, status=400)
    columns: List[Dict[str, Any]] = dataset.get('columns') or []
    rows: List[Dict[str, Any]] = dataset.get('rows') or []
    filtered_rows = _filter_table_rows(rows, columns, filters)
    export_columns = [column for column in columns if column.get('export', True)] or columns
    filename = dataset.get('filename') or 'table-data'
    safe_name = _sanitize_identifier(filename) or 'table_data'
    timestamp = timezone.now().strftime('%Y%m%d-%H%M%S')
    base_name = f"{safe_name}-{timestamp}"
    headers = [column.get('label') or column.get('field', '') for column in export_columns]
    field_names = [column.get('field') for column in export_columns]

    if export_format == 'xlsx':
        if openpyxl is None:
            message = _localise_text(lang, 'Excel export is not available on this server.', 'امکان تهیه فایل اکسل وجود ندارد.')
            return JsonResponse({'error': message}, status=400)
        workbook = openpyxl.Workbook()
        worksheet = workbook.active
        worksheet.title = 'Export'
        worksheet.append(headers)
        for row in filtered_rows:
            worksheet.append([
                _normalise_record_value(row.get(field, ''))
                for field in field_names
            ])
        stream = BytesIO()
        workbook.save(stream)
        stream.seek(0)
        response = HttpResponse(
            stream.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename="{base_name}.xlsx"'
        return response

    output = StringIO()
    writer = csv.writer(output, lineterminator='\n')
    writer.writerow(headers)
    for row in filtered_rows:
        writer.writerow([
            _normalise_record_value(row.get(field, ''))
            for field in field_names
        ])
    content = '\ufeff' + output.getvalue()
    response = HttpResponse(content, content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{base_name}.csv"'
    return response


def generate_call_samples(project: Project, replenish: bool = False) -> None:
    """
    Generate call samples for a project based on its quotas.

    For each quota cell (city × age range) this function selects up to
    three times the target count of respondent phone numbers.  Samples
    are drawn from the ``Person`` and ``Mobile`` tables, excluding any
    numbers that have already been assigned or interviewed for the
    project.  If ``replenish`` is False (default) the existing samples
    for the project are cleared before sampling anew.  When
    ``replenish`` is True, only missing samples are topped up.

    A fallback mechanism ensures that if insufficient candidates are
    available for a strict city+age cell, the same city without age
    filtering is used, and finally the entire respondent bank is
    considered.  This avoids situations where a quota cell has no
    viable respondents due to prior assignments or interviews.

    Args:
        project: The project for which to generate call samples.
        replenish: If True, only top up shortage; if False, rebuild
            all samples from scratch.
    """
    if project.sample_source != Project.SampleSource.DATABASE:
        return

    quotas = Quota.objects.filter(project=project).order_by('city', 'age_start', 'age_end')
    if replenish:
        open_map = {
            row['quota_id']: row['total']
            for row in CallSample.objects.filter(project=project, completed=False)
            .values('quota_id')
            .annotate(total=Count('id'))
        }
    else:
        # Clear existing samples when regenerating from scratch
        CallSample.objects.filter(project=project).delete()
        open_map: Dict[int, int] = {}
    # Keep track of numbers already assigned or interviewed for this project
    assigned_mobiles = set(
        CallSample.objects.filter(project=project).values_list('mobile__mobile', flat=True)
    )
    interviewed_mobiles = set(
        Interview.objects.filter(project=project, person__mobiles__isnull=False)
        .values_list('person__mobiles__mobile', flat=True)
    )
    exclude_mobiles: set[str] = assigned_mobiles | interviewed_mobiles
    current_year = timezone.now().year

    for q in quotas:
        remaining_gap = int(q.target_count) - int(q.assigned_count)
        if remaining_gap < 0:
            remaining_gap = 0
        desired_total = remaining_gap * 3
        existing_open = open_map.get(q.pk, 0)
        if replenish:
            to_create = max(desired_total - existing_open, 0)
        else:
            to_create = desired_total
        if to_create <= 0:
            continue
        filters: List[Tuple[Optional[str], Optional[Tuple[int, int]], Optional[str]]] = []
        age_tuple: Optional[Tuple[int, int]] = None
        if q.age_start is not None and q.age_end is not None:
            age_tuple = (int(q.age_start), int(q.age_end))
        filters.append((q.city, age_tuple, q.gender))
        if age_tuple:
            filters.append((q.city, None, q.gender))
        if q.city:
            filters.append((None, age_tuple, q.gender))
        if q.gender:
            filters.append((q.city, age_tuple, None))
        filters.append((None, None, None))

        candidates: List[str] = []
        seen_candidates: set[str] = set()
        for city_filter, age_filter, gender_filter in filters:
            qs = Person.objects.filter(mobiles__isnull=False)
            if city_filter:
                qs = qs.filter(city_name=city_filter)
            if gender_filter:
                qs = qs.filter(gender=gender_filter)
            if age_filter:
                birth_min = current_year - int(age_filter[1])
                birth_max = current_year - int(age_filter[0])
                qs = qs.filter(birth_year__gte=birth_min, birth_year__lte=birth_max)
            qs = (
                qs.exclude(mobiles__mobile__in=exclude_mobiles)
                .exclude(national_code__in=seen_candidates)
                .distinct()
            )
            batch = list(qs.values_list('national_code', flat=True)[: (to_create * 8)])
            for code in batch:
                if code not in seen_candidates:
                    seen_candidates.add(code)
                    candidates.append(code)
            if len(candidates) >= to_create:
                break
        if not candidates:
            continue
        random.shuffle(candidates)
        selected_ids = candidates[:to_create]
        persons = Person.objects.filter(national_code__in=selected_ids).prefetch_related('mobiles')
        created = 0
        for person in persons:
            mob = person.mobiles.first()
            if not mob:
                continue
            CallSample.objects.create(
                project=project,
                quota=q,
                person=person,
                mobile=mob,
                assigned_to=None,
                assigned_at=None,
                completed=False,
                completed_at=None,
            )
            exclude_mobiles.add(mob.mobile)
            created += 1
        if created:
            open_map[q.pk] = existing_open + created


def _assign_uploaded_sample(project: Project, user: User) -> Optional[UploadedSampleEntry]:
    """Return an uploaded sample assigned to the user or grab a new one."""

    sample = (
        UploadedSampleEntry.objects.filter(project=project, assigned_to=user, completed=False)
        .order_by('assigned_at', 'pk')
        .first()
    )
    if sample:
        return sample
    sample = (
        UploadedSampleEntry.objects.filter(project=project, assigned_to__isnull=True, completed=False)
        .order_by('pk')
        .first()
    )
    if sample:
        sample.assigned_to = user
        sample.assigned_at = timezone.now()
        sample.save(update_fields=['assigned_to', 'assigned_at'])
    return sample


def _get_accessible_projects(user: User, panel: str | None = None) -> List[Project]:
    """Return a list of projects accessible to the user.

    If ``panel`` is provided, only projects where the user has that panel
    permission are returned.  Organisation users see all projects for
    which they have a membership (typically all that they created).
    """
    if getattr(user, 'is_superuser', False):
        return list(Project.objects.all().order_by('pk'))
    qs = Project.objects.filter(memberships__user=user)
    if panel:
        filter_kwargs = {f"memberships__{panel}": True}
        qs = qs.filter(**filter_kwargs)
    projects: List[Project] = []
    for project in qs.distinct():
        if _project_deadline_locked_for_user(project, user):
            continue
        projects.append(project)
    return projects


def _resolve_interview_demographics(interview: Interview) -> Tuple[Optional[str], Optional[int], Optional[str]]:
    """Return the city, age, and gender data points for an interview."""

    city_name = interview.city or (interview.person.city_name if interview.person else None)
    if city_name:
        city_name = city_name.strip()

    age_value: Optional[int] = interview.age
    if age_value is None:
        birth_year_source = interview.birth_year
        if birth_year_source is None and interview.person and interview.person.birth_year:
            birth_year_source = interview.person.birth_year
        derived_age = calculate_age_from_birth_info(birth_year_source, None)
        if derived_age is not None:
            age_value = derived_age

    gender_value = gender_value_from_boolean(interview.gender)
    if not gender_value and interview.person:
        gender_value = normalize_gender_value(interview.person.gender)

    return city_name, age_value, gender_value


def _is_truthy(value: Any) -> bool:
    """Return True when a POSTed checkbox-like value is affirmative."""

    if value is None:
        return False
    return str(value).strip().lower() in {'1', 'true', 'on', 'yes'}


def _serialise_project_types_value(form: ProjectForm) -> str:
    """Return a comma-separated string of project types for the form."""

    value = form['types'].value()
    if isinstance(value, (list, tuple)):
        return ', '.join(value)
    if isinstance(value, str):
        return value
    instance_types = getattr(form.instance, 'types', None) or []
    if instance_types:
        return ', '.join(instance_types)
    return ''


def _project_form_context(form: ProjectForm, title: str) -> Dict[str, Any]:
    """Build the template context for the project create/edit form."""

    return {
        'form': form,
        'title': title,
        'required_headers': SAMPLE_REQUIRED_HEADERS,
        'call_result_headers': CALL_RESULT_REQUIRED_HEADERS,
        'project': form.instance,
        'types_initial': _serialise_project_types_value(form),
    }


@login_required
def project_list(request: HttpRequest) -> HttpResponse:
    """List projects accessible to the logged in organisation user."""
    user = request.user
    lang = _get_lang(request)
    if not _user_is_organisation(user):
        messages.warning(request, 'Access denied: only organisation accounts can manage projects.')
        return redirect('home')
    projects = _get_accessible_projects(user)
    context = {
        'projects': projects,
        'lang': lang,
        'breadcrumbs': _build_breadcrumbs(
            lang,
            (_localise_text(lang, 'Projects', 'پروژه‌ها'), ''),
        ),
    }
    return render(request, 'projects_list.html', context)


@login_required
def project_add(request: HttpRequest) -> HttpResponse:
    """Create a new project and assign the creator membership to it."""
    user = request.user
    lang = _get_lang(request)
    if not _user_is_organisation(user):
        messages.warning(request, 'Access denied: only organisation accounts can create projects.')
        return redirect('home')
    if request.method == 'POST':
        form = ProjectForm(request.POST, request.FILES)
        new_upload = bool(request.FILES.get('sample_upload'))
        new_call_upload = bool(request.FILES.get('call_result_upload'))
        if form.is_valid():
            try:
                with transaction.atomic():
                    project = form.save(commit=False)
                    project.filled_samples = 0
                    project.save()
                    if new_upload:
                        ingest_project_sample_upload(project)
                    if project.call_result_source == Project.CallResultSource.DEFAULT:
                        clear_project_call_results(project)
                    elif new_call_upload:
                        ingest_project_call_result_upload(project)
            except SampleUploadError as exc:
                form.add_error('sample_upload', str(exc))
            except CallResultUploadError as exc:
                form.add_error('call_result_upload', str(exc))
            else:
                Membership.objects.create(
                    user=user,
                    project=project,
                    is_owner=True,
                    database_management=True,
                    quota_management=True,
                    collection_management=True,
                    collection_performance=True,
                    telephone_interviewer=True,
                    fieldwork_interviewer=True,
                    focus_group_panel=True,
                    qc_management=True,
                    qc_performance=True,
                    voice_review=True,
                    callback_qc=True,
                    coding=True,
                    statistical_health_check=True,
                    tabulation=True,
                    statistics=True,
                    funnel_analysis=True,
                    conjoint_analysis=True,
                    segmentation_analysis=True,
                )
                messages.success(request, 'Project created successfully.')
                log_activity(user, 'Created project', f"Project {project.pk}: {project.name}")
                notify_project_started(project, initiator=user)
                return redirect('project_list')
    else:
        form = ProjectForm()
    title = _localise_text(lang, 'Add Project', 'ایجاد پروژه')
    context = _project_form_context(form, title)
    context.update(
        {
            'lang': lang,
            'breadcrumbs': _build_breadcrumbs(
                lang,
                (_localise_text(lang, 'Projects', 'پروژه‌ها'), reverse('project_list')),
                (title, ''),
            ),
        }
    )
    return render(request, 'project_form.html', context)


@login_required
def project_edit(request: HttpRequest, project_id: int) -> HttpResponse:
    """Edit an existing project accessible to the organisation user."""
    user = request.user
    lang = _get_lang(request)
    if not _user_is_organisation(user):
        messages.warning(request, 'Access denied: only organisation accounts can edit projects.')
        return redirect('home')
    project = get_object_or_404(Project, pk=project_id)
    # ensure the user has a membership to this project
    if not Membership.objects.filter(project=project, user=user).exists():
        messages.error(request, 'You do not have permission to edit this project.')
        return redirect('project_list')
    if request.method == 'POST':
        form = ProjectForm(request.POST, request.FILES, instance=project)
        new_upload = bool(request.FILES.get('sample_upload'))
        new_call_upload = bool(request.FILES.get('call_result_upload'))
        if form.is_valid():
            try:
                with transaction.atomic():
                    project = form.save()
                    if new_upload:
                        ingest_project_sample_upload(project)
                    if project.call_result_source == Project.CallResultSource.DEFAULT:
                        clear_project_call_results(project)
                    elif new_call_upload:
                        ingest_project_call_result_upload(project)
            except SampleUploadError as exc:
                form.add_error('sample_upload', str(exc))
            except CallResultUploadError as exc:
                form.add_error('call_result_upload', str(exc))
            else:
                messages.success(request, 'Project updated successfully.')
                log_activity(user, 'Updated project', f"Project {project.pk}: {project.name}")
                return redirect('project_list')
    else:
        form = ProjectForm(instance=project)
    title = _localise_text(lang, 'Edit Project', 'ویرایش پروژه')
    context = _project_form_context(form, title)
    context.update(
        {
            'lang': lang,
            'breadcrumbs': _build_breadcrumbs(
                lang,
                (_localise_text(lang, 'Projects', 'پروژه‌ها'), reverse('project_list')),
                (project.name or title, reverse('project_edit', args=[project.pk])),
                (title, ''),
            ),
        }
    )
    return render(request, 'project_form.html', context)


@login_required
def project_dataset_append(request: HttpRequest, project_id: int) -> HttpResponse:
    """Allow authorised users to append new respondent rows mid-project."""

    lang = request.session.get('lang', 'en')
    project = get_object_or_404(Project, pk=project_id)
    membership = (
        Membership.objects.filter(project=project, user=request.user)
        .select_related('project')
        .first()
    )
    if not membership:
        messages.error(request, 'Access denied: you are not a member of this project.')
        return redirect('project_list')
    if not (
        membership.is_owner
        or membership.database_management
        or membership.telephone_interviewer
    ):
        messages.error(request, 'Access denied: this upload is limited to owners or database/telephone panel members.')
        return redirect('project_list')
    if not project.status:
        messages.error(request, 'Dataset uploads are only allowed while the project is collecting data.')
        return redirect('project_list')

    sample_metadata = project.sample_upload_metadata or {}
    if request.method == 'POST':
        form = ProjectSampleAppendForm(request.POST, request.FILES)
        if form.is_valid():
            workbook = form.cleaned_data['workbook']
            try:
                if project.sample_source == Project.SampleSource.UPLOAD:
                    result = append_project_sample_upload(project, uploaded_file=workbook)
                else:
                    result = append_project_respondent_bank(project, uploaded_file=workbook)
            except SampleUploadError as exc:
                form.add_error('workbook', str(exc))
            else:
                if project.sample_source == Project.SampleSource.DATABASE:
                    generate_call_samples(project, replenish=True)
                success_text = _localise_text(
                    lang,
                    f'Appended {result.appended_rows} new rows (skipped {result.duplicate_rows} duplicates).',
                    f'{result.appended_rows} ردیف جدید اضافه شد و {result.duplicate_rows} ردیف تکراری حذف شد.',
                )
                messages.success(request, success_text)
                return redirect('project_dataset_append', project_id=project.pk)
    else:
        form = ProjectSampleAppendForm()

    context = {
        'form': form,
        'project': project,
        'lang': lang,
        'sample_source': project.sample_source,
        'required_headers': SAMPLE_REQUIRED_HEADERS,
        'sample_metadata': sample_metadata,
    }
    return render(request, 'project_dataset_append.html', context)


@login_required
@require_POST
def project_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete a project and its associated memberships (organisation only)."""
    user = request.user
    if not _user_is_organisation(user):
        messages.warning(request, 'Access denied.')
        return redirect('project_list')
    project = get_object_or_404(Project, pk=pk)
    if not Membership.objects.filter(project=project, user=user).exists():
        messages.error(request, 'You do not have permission to delete this project.')
        return redirect('project_list')
    project_name = project.name
    project.delete()
    messages.success(request, 'Project deleted successfully.')
    # log activity
    log_activity(user, 'Deleted project', f"Project {pk}: {project_name}")
    return redirect('project_list')


@login_required
def membership_list(request: HttpRequest) -> HttpResponse:
    """Display memberships for the organisation user."""
    user = request.user
    if not _user_is_organisation(user):
        messages.warning(request, 'Access denied: only organisation accounts can manage memberships.')
        return redirect('home')
    accessible_projects = _get_accessible_projects(user)
    if not accessible_projects:
        locked = _get_locked_projects(user)
        if locked:
            locked_names = ', '.join(sorted({p.name for p in locked}))
            messages.error(
                request,
                f'Access denied: project deadlines have passed ({locked_names}). Only the owner can view memberships.',
            )
        else:
            messages.error(request, 'Access denied: there are no projects available to display memberships.')
        return redirect('home')
    # list all memberships for projects of this organisation
    memberships = Membership.objects.filter(project__in=accessible_projects).distinct()
    # map field names to human readable labels for display
    return render(
        request,
        'membership_list.html',
        {
            'memberships': memberships,
            'panel_labels': MEMBERSHIP_PANEL_LABELS,
            'lang': request.session.get('lang', 'en'),
        },
    )


@login_required
def membership_add(request: HttpRequest) -> HttpResponse:
    """Assign a user to a project with panel permissions (organisation only)."""
    user = request.user
    if not _user_is_organisation(user):
        messages.warning(request, 'Access denied: only organisation accounts can manage memberships.')
        return redirect('home')
    lang = request.session.get('lang', 'en')
    # projects the organisation can assign users to
    accessible_projects = _get_accessible_projects(user)
    if not accessible_projects:
        locked = _get_locked_projects(user)
        if locked:
            locked_names = ', '.join(sorted({p.name for p in locked}))
            messages.error(
                request,
                f'Access denied: project deadlines have passed ({locked_names}). Only the owner can continue to manage memberships.',
            )
        else:
            messages.error(request, 'Access denied: there are no projects available for membership changes.')
        return redirect('home')
    workbook_form = MembershipWorkbookForm()
    if request.method == 'POST':
        form = UserToProjectForm(request.POST)
        form.fields['project'].queryset = Project.objects.filter(pk__in=[p.pk for p in accessible_projects])
        if form.is_valid():
            project = form.cleaned_data['project']
            emails = form.cleaned_data['emails']
            successes: list[str] = []
            errors: list[str] = []
            base_kwargs = {}
            for field in form.fields:
                if field in ('emails', 'project', 'title_custom'):
                    continue
                base_kwargs[field] = form.cleaned_data[field]
            requested_owner = bool(base_kwargs.get('is_owner'))
            owner_assigned = False
            project_has_owner = Membership.objects.filter(project=project, is_owner=True).exists()
            for email in emails:
                try:
                    target_user = User.objects.get(username=email)
                except User.DoesNotExist:
                    errors.append(f'User {email} does not exist.')
                    continue
                if Membership.objects.filter(user=target_user, project=project).exists():
                    errors.append(f'{email} is already assigned to this project.')
                    continue
                mem_kwargs = base_kwargs.copy()
                is_owner_for_row = False
                if requested_owner and not owner_assigned:
                    is_owner_for_row = True
                    owner_assigned = True
                elif not project_has_owner:
                    is_owner_for_row = True
                mem_kwargs['is_owner'] = is_owner_for_row
                if is_owner_for_row:
                    Membership.objects.filter(project=project, is_owner=True).update(is_owner=False)
                    project_has_owner = True
                membership = Membership.objects.create(user=target_user, project=project, **mem_kwargs)
                successes.append(email)
                log_activity(user, 'Added membership', f"User {target_user.username} to Project {project.pk}")
                notify_membership_added(membership, actor=user)
            if successes:
                added = ', '.join(successes)
                messages.success(
                    request,
                    _bilingual(
                        f"Added memberships for: {added}",
                        f"عضویت کاربران افزوده شد: {added}",
                    ),
                )
                if errors:
                    error_summary = '; '.join(errors)
                    messages.warning(
                        request,
                        _bilingual(
                            f"Some addresses were skipped: {error_summary}",
                            f"برخی ایمیل‌ها اضافه نشدند: {error_summary}",
                        ),
                    )
                return redirect('membership_list')
            error_summary = '; '.join(errors) if errors else 'No memberships were created.'
            messages.error(
                request,
                _bilingual(
                    f"Could not add any memberships: {error_summary}",
                    f"هیچ عضوی اضافه نشد: {error_summary}",
                ),
            )
    else:
        form = UserToProjectForm()
        form.fields['project'].queryset = Project.objects.filter(pk__in=[p.pk for p in accessible_projects])
    return render(
        request,
        'membership_form.html',
        {
            'form': form,
            'title': 'Add User to Project',
            'lang': lang,
            'workbook_form': workbook_form,
            'workbook_template_url': reverse('membership_export_workbook'),
        },
    )


@login_required
def membership_export_workbook(request: HttpRequest) -> HttpResponse:
    """Stream the membership workbook for all accessible projects."""

    user = request.user
    if not _user_is_organisation(user):
        messages.warning(request, _bilingual('Access denied.', 'دسترسی مجاز نیست.'))
        return redirect('home')
    projects = _get_accessible_projects(user)
    if not projects:
        messages.error(
            request,
            _bilingual('No projects are available for export.', 'پروژه‌ای برای خروجی گرفتن وجود ندارد.'),
        )
        return redirect('membership_list')
    memberships = (
        Membership.objects.filter(project__in=projects)
        .select_related('user', 'project')
        .order_by('project__name', 'user__username')
    )
    try:
        workbook_stream = export_memberships_workbook(memberships)
    except MembershipWorkbookError as exc:
        messages.error(
            request,
            _bilingual('Unable to generate the workbook.', 'امکان ساخت فایل اکسل وجود ندارد.') + f' ({exc})',
        )
        return redirect('membership_list')
    filename = timezone.now().strftime('membership-workbook-%Y%m%d%H%M%S.xlsx')
    response = HttpResponse(
        workbook_stream.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
@require_POST
def membership_import_workbook(request: HttpRequest) -> HttpResponse:
    """Handle workbook uploads and delegate to the import helper."""

    user = request.user
    if not _user_is_organisation(user):
        messages.warning(request, _bilingual('Access denied.', 'دسترسی مجاز نیست.'))
        return redirect('home')
    projects = _get_accessible_projects(user)
    if not projects:
        messages.error(
            request,
            _bilingual('No projects are available for import.', 'پروژه‌ای برای وارد کردن وجود ندارد.'),
        )
        return redirect('membership_add')
    form = MembershipWorkbookForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(
            request,
            _bilingual('Please upload a valid Excel workbook.', 'لطفاً فایل اکسل معتبر بارگذاری کنید.'),
        )
        return redirect('membership_add')
    workbook = form.cleaned_data['workbook']
    try:
        result = import_memberships_workbook(workbook, accessible_projects=list(projects))
    except MembershipWorkbookError as exc:
        messages.error(
            request,
            _bilingual('Import failed:', 'وارد کردن ناموفق بود:') + f' {exc}',
        )
        return redirect('membership_add')
    if result.created:
        messages.success(
            request,
            _bilingual(
                f'Created {result.created} memberships from the workbook.',
                f'{result.created} عضویت جدید از فایل اکسل ایجاد شد.',
            ),
        )
    if result.replaced:
        messages.info(
            request,
            _bilingual(
                f'Replaced {result.replaced} existing memberships.',
                f'{result.replaced} عضویت قبلی جایگزین شد.',
            ),
        )
    if result.errors:
        preview = '; '.join(result.errors[:5])
        messages.warning(
            request,
            _bilingual(
                f'Some rows were skipped: {preview}',
                f'برخی ردیف‌ها نادیده گرفته شدند: {preview}',
            ),
        )
    return redirect('membership_list')


@login_required
@require_http_methods(["POST"])
def membership_message_send(request: HttpRequest) -> JsonResponse:
    """Send a custom notification to selected project members."""

    user = request.user
    if not _user_is_organisation(user):
        return JsonResponse({'ok': False, 'message': 'Access denied.'}, status=403)

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'ok': False, 'message': 'Invalid payload.'}, status=400)

    raw_message = str(payload.get('message') or '').strip()
    if not raw_message:
        return JsonResponse({'ok': False, 'message': 'Message is required.'}, status=400)
    if len(raw_message) > 500:
        return JsonResponse({'ok': False, 'message': 'Messages are limited to 500 characters.'}, status=400)

    user_ids = payload.get('user_ids')
    if not isinstance(user_ids, list):
        return JsonResponse({'ok': False, 'message': 'No recipients selected.'}, status=400)
    try:
        id_set = {int(value) for value in user_ids}
    except (TypeError, ValueError):
        return JsonResponse({'ok': False, 'message': 'Invalid recipient identifiers.'}, status=400)
    if not id_set:
        return JsonResponse({'ok': False, 'message': 'No recipients selected.'}, status=400)

    projects = _get_accessible_projects(user)
    if not projects:
        return JsonResponse({'ok': False, 'message': 'No accessible projects available.'}, status=400)

    memberships = (
        Membership.objects.filter(project__in=projects, user_id__in=id_set)
        .select_related('user')
        .order_by('user_id')
    )
    recipients: List[User] = []
    seen: set[int] = set()
    for membership in memberships:
        if membership.user_id in seen:
            continue
        seen.add(membership.user_id)
        recipients.append(membership.user)

    if not recipients:
        return JsonResponse({'ok': False, 'message': 'No valid recipients found.'}, status=400)

    notifications = notify_custom_message(
        recipients,
        message_en=raw_message,
        message_fa=raw_message,
        actor=user,
    )
    log_activity(user, 'Sent custom membership message', f"Recipients: {len(notifications)}")

    skipped = list(sorted(id_set.difference(seen)))
    return JsonResponse(
        {
            'ok': True,
            'created': len(notifications),
            'skipped': skipped,
        }
    )


@login_required
def membership_edit(request: HttpRequest, membership_id: int) -> HttpResponse:
    """Edit membership panel permissions (organisation only)."""
    user = request.user
    if not _user_is_organisation(user):
        messages.warning(request, 'Access denied: only organisation accounts can edit memberships.')
        return redirect('home')
    membership = get_object_or_404(Membership, pk=membership_id)
    # ensure the organisation has access to this membership's project
    if not Membership.objects.filter(project=membership.project, user=user).exists():
        messages.error(request, 'You do not have permission to edit this membership.')
        return redirect('membership_list')
    if _project_deadline_locked_for_user(membership.project, user):
        messages.error(
            request,
            'Access denied: the project deadline has passed and only the owner may update memberships.',
        )
        return redirect('membership_list')
    panel_fields = [
        f for f in UserToProjectForm().fields if f not in ('emails', 'project', 'title_custom', 'is_owner')
    ]
    if request.method == 'POST':
        form = UserToProjectForm(request.POST)
        form.fields['project'].queryset = Project.objects.filter(pk=membership.project.pk)
        form.fields['emails'].widget = forms.HiddenInput()  # type: ignore
        # set initial project field to membership.project
        if form.is_valid():
            for field in panel_fields:
                setattr(membership, field, form.cleaned_data[field])
            membership.is_owner = form.cleaned_data['is_owner']
            membership.save()
            if membership.is_owner:
                Membership.objects.filter(project=membership.project).exclude(pk=membership.pk).update(is_owner=False)
            else:
                if not Membership.objects.filter(project=membership.project, is_owner=True).exclude(pk=membership.pk).exists():
                    replacement = (
                        Membership.objects.filter(project=membership.project)
                        .exclude(pk=membership.pk)
                        .order_by('start_work', 'pk')
                        .first()
                    )
                    if replacement:
                        replacement.is_owner = True
                        replacement.save(update_fields=['is_owner'])
                    else:
                        membership.is_owner = True
                        membership.save(update_fields=['is_owner'])
            messages.success(request, 'Membership updated successfully.')
            # log activity
            log_activity(user, 'Updated membership', f"Membership {membership_id}")
            return redirect('membership_list')
    else:
        initial = {'emails': membership.user.email, 'project': membership.project, 'title': membership.title}
        for field in panel_fields:
            initial[field] = getattr(membership, field)
        initial['is_owner'] = membership.is_owner
        form = UserToProjectForm(initial=initial)
        form.fields['project'].queryset = Project.objects.filter(pk=membership.project.pk)
        form.fields['emails'].widget = forms.HiddenInput()  # type: ignore
        form.fields['project'].widget = forms.HiddenInput()  # type: ignore
    return render(
        request,
        'membership_form.html',
        {
            'form': form,
            'title': 'Edit Membership',
            'lang': request.session.get('lang', 'en'),
        },
    )


@login_required
@require_POST
def membership_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Remove a user from a project (organisation only)."""
    user = request.user
    if not _user_is_organisation(user):
        messages.warning(request, 'Access denied.')
        return redirect('membership_list')
    membership = get_object_or_404(Membership, pk=pk)
    # ensure the organisation has access to this project
    if not Membership.objects.filter(project=membership.project, user=user).exists():
        messages.error(request, 'You do not have permission to remove this membership.')
        return redirect('membership_list')
    if _project_deadline_locked_for_user(membership.project, user):
        messages.error(
            request,
            'Access denied: the project deadline has passed and only the owner may update memberships.',
        )
        return redirect('membership_list')
    membership_user = membership.user.username
    project_id = membership.project.pk
    was_owner = membership.is_owner
    membership.delete()
    if was_owner:
        replacement = (
            Membership.objects.filter(project_id=project_id)
            .order_by('start_work', 'pk')
            .first()
        )
        if replacement:
            replacement.is_owner = True
            replacement.save(update_fields=['is_owner'])
    messages.success(request, 'Membership removed.')
    # log activity
    log_activity(user, 'Removed membership', f"User {membership_user} from Project {project_id}")
    return redirect('membership_list')


@login_required
def quota_management(request: HttpRequest) -> HttpResponse:
    """
    Quota management panel allowing users to define and edit quotas.

    On GET requests the view displays a form for selecting a project and
    defining city and age quotas.  If a project has existing quotas, the
    form is prefilled with the current percentage allocations and a
    summary table of assigned versus target counts is shown.  The
    selected project is remembered in the session so that users can
    navigate away and return to see the same project's quotas.

    On POST requests the view validates the submitted percentages,
    calculates target counts for each city/age cell based on the
    project's sample size and stores them in the ``Quota`` table.  After
    saving, call samples are regenerated from scratch.
    """
    lang = request.session.get('lang', 'en')
    user = request.user
    if not _user_has_panel(user, 'quota_management'):
        messages.error(request, 'Access denied: you do not have quota management permissions.')
        return redirect('home')
    projects = _get_accessible_projects(user, 'quota_management')
    if not projects:
        locked = _get_locked_projects(user, panel='quota_management')
        if locked:
            locked_names = ', '.join(sorted({p.name for p in locked}))
            messages.error(
                request,
                f'Access denied: project deadlines have passed ({locked_names}). Only the owner can continue to manage quotas.',
            )
        else:
            messages.error(request, 'Access denied: there are no projects available for quota management.')
        return redirect('home')

    # Determine selected project from query param or session
    project_param = request.GET.get('project') or request.session.get('quota_project')
    selected_project: Project | None = None
    if project_param:
        try:
            selected_project = Project.objects.get(pk=project_param)
        except Project.DoesNotExist:
            selected_project = None
        else:
            if _project_deadline_locked_for_user(selected_project, user):
                messages.error(
                    request,
                    'Access denied: the project deadline has passed and only the owner may manage quotas.',
                )
                selected_project = None
            else:
                request.session['quota_project'] = selected_project.pk

    if request.method == 'POST':
        project_id = request.POST.get('project')
        city_data_json = request.POST.get('city_data') or '[]'
        age_data_json = request.POST.get('age_data') or '[]'
        gender_data_json = request.POST.get('gender_data') or '[]'
        city_enabled = _is_truthy(request.POST.get('enable_city'))
        age_enabled = _is_truthy(request.POST.get('enable_age'))
        gender_enabled = _is_truthy(request.POST.get('enable_gender'))
        if not project_id:
            messages.error(request, 'Invalid form submission.')
            return redirect('quota_management')
        try:
            project = Project.objects.get(pk=project_id)
        except Project.DoesNotExist:
            messages.error(request, 'Project not found.')
            return redirect('quota_management')
        if _project_deadline_locked_for_user(project, user):
            messages.error(
                request,
                'Access denied: the project deadline has passed and only the owner may manage quotas.',
            )
            return redirect('quota_management')
        request.session['quota_project'] = project.pk
        # ensure user has membership or organisation rights
        if not _user_is_organisation(user) and not Membership.objects.filter(project=project, user=user, quota_management=True).exists():
            messages.error(request, 'You do not have quota permissions for this project.')
            return redirect('quota_management')
        try:
            city_data: List[Dict[str, Any]] = json.loads(city_data_json)
            age_data: List[Dict[str, Any]] = json.loads(age_data_json)
            gender_data: List[Dict[str, Any]] = json.loads(gender_data_json)
        except json.JSONDecodeError:
            messages.error(request, 'Invalid quota data.')
            return redirect('quota_management')

        def _parse_city_entries() -> List[Dict[str, Any]]:
            if not city_enabled:
                return [{'value': None, 'quota': 100.0}]
            entries: List[Dict[str, Any]] = []
            total = 0.0
            for item in city_data:
                name = str(item.get('city') or '').strip()
                if not name:
                    continue
                quota_pct = float(item.get('quota') or 0)
                total += quota_pct
                entries.append({'value': name, 'quota': quota_pct})
            if not entries:
                raise ValueError('City quotas are required when the city dimension is enabled.')
            if abs(total - 100.0) > 0.01:
                raise ValueError('City quotas must sum to 100%.')
            return entries

        def _parse_age_entries() -> List[Dict[str, Any]]:
            if not age_enabled:
                return [{'start': None, 'end': None, 'quota': 100.0}]
            entries: List[Dict[str, Any]] = []
            total = 0.0
            ranges: List[Tuple[int, int]] = []
            for item in age_data:
                start = int(item.get('start'))
                end = int(item.get('end'))
                if start >= end:
                    raise ValueError('Age range start must be less than end.')
                quota_pct = float(item.get('quota') or 0)
                total += quota_pct
                entries.append({'start': start, 'end': end, 'quota': quota_pct})
                ranges.append((start, end))
            if not entries:
                raise ValueError('At least one age range is required when the age dimension is enabled.')
            ranges.sort(key=lambda rng: rng[0])
            for idx in range(1, len(ranges)):
                if ranges[idx][0] < ranges[idx - 1][1]:
                    raise ValueError('Age ranges must not overlap.')
            if abs(total - 100.0) > 0.01:
                raise ValueError('Age quotas must sum to 100%.')
            return entries

        def _parse_gender_entries() -> List[Dict[str, Any]]:
            if not gender_enabled:
                return [{'value': None, 'quota': 100.0}]
            entries: List[Dict[str, Any]] = []
            total = 0.0
            for item in gender_data:
                normalized = normalize_gender_value(item.get('value'))
                if not normalized:
                    continue
                quota_pct = float(item.get('quota') or 0)
                total += quota_pct
                entries.append({'value': normalized, 'quota': quota_pct})
            if not entries:
                raise ValueError('Select at least one gender when the gender dimension is enabled.')
            if abs(total - 100.0) > 0.01:
                raise ValueError('Gender quotas must sum to 100%.')
            return entries

        try:
            city_entries = _parse_city_entries()
            age_entries = _parse_age_entries()
            gender_entries = _parse_gender_entries()
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect('quota_management')

        CallSample.objects.filter(project=project).delete()
        Quota.objects.filter(project=project).delete()
        sample_size = int(project.sample_size)
        quota_cells: List[Tuple[Optional[str], Optional[int], Optional[int], Optional[str], int]] = []
        for city_entry in city_entries:
            city_name = city_entry['value']
            city_pct = float(city_entry['quota']) / 100.0
            for age_entry in age_entries:
                age_start = age_entry.get('start')
                age_end = age_entry.get('end')
                age_pct = float(age_entry['quota']) / 100.0
                for gender_entry in gender_entries:
                    gender_value = gender_entry['value']
                    gender_pct = float(gender_entry['quota']) / 100.0
                    target_count = int(round(sample_size * city_pct * age_pct * gender_pct))
                    quota_cells.append((city_name, age_start, age_end, gender_value, target_count))

        diff = sample_size - sum(cell[4] for cell in quota_cells)
        if quota_cells and diff != 0:
            city_name, age_start, age_end, gender_value, count = quota_cells[0]
            quota_cells[0] = (city_name, age_start, age_end, gender_value, max(count + diff, 0))

        for city_name, age_start, age_end, gender_value, count in quota_cells:
            Quota.objects.create(
                project=project,
                city=city_name or None,
                age_start=age_start,
                age_end=age_end,
                gender=gender_value,
                target_count=count,
                assigned_count=0,
            )
        log_activity(user, 'Saved quotas', f"Project {project.pk}")
        if project.sample_source == Project.SampleSource.DATABASE:
            try:
                generate_call_samples(project, replenish=False)
            except Exception:
                pass
        messages.success(request, 'Quotas saved successfully.')
        return redirect(f"{reverse('quota_management')}?project={project.pk}")

    # Build context for GET requests
    # union of all cities present in database and selected project's quotas
    db_cities = {
        value
        for value in Person.objects.values_list('city_name', flat=True)
        if value
    }
    if selected_project:
        quota_cities = {
            value
            for value in Quota.objects.filter(project=selected_project).values_list('city', flat=True)
            if value
        }
    else:
        quota_cities = set()
    cities = sorted(db_cities | quota_cities)
    gender_options = [
        {'value': 'male', 'label_en': 'Male', 'label_fa': 'مرد'},
        {'value': 'female', 'label_en': 'Female', 'label_fa': 'زن'},
    ]
    dimension_state = {'city': True, 'age': True, 'gender': False}
    prefill_payload: Dict[str, Any] = {
        'city_enabled': dimension_state['city'],
        'age_enabled': dimension_state['age'],
        'gender_enabled': dimension_state['gender'],
        'cities': {},
        'ages': [],
        'genders': [],
    }
    context: Dict[str, Any] = {
        'projects': projects,
        'cities': cities,
        'selected_project': selected_project,
        'gender_options': gender_options,
        'dimension_state': dimension_state,
        'prefill_json': json.dumps(prefill_payload, ensure_ascii=False),
        'lang': lang,
    }
    if selected_project:
        quotas = list(Quota.objects.filter(project=selected_project))
        if quotas:
            dimension_state = {
                'city': any(q.city for q in quotas),
                'age': any(q.age_start is not None for q in quotas),
                'gender': any(q.gender for q in quotas),
            }
        else:
            dimension_state = context['dimension_state']
        context['dimension_state'] = dimension_state

        prefill_payload = {
            'city_enabled': dimension_state['city'],
            'age_enabled': dimension_state['age'],
            'gender_enabled': dimension_state['gender'],
            'cities': {},
            'ages': [],
            'genders': [],
        }

        if quotas:
            success_counts: Dict[int, int] = defaultdict(int)
            successful_interviews = (
                Interview.objects.filter(project=selected_project, status=True)
                .select_related('person')
            )
            for interview in successful_interviews:
                city_name, age_value, gender_value = _resolve_interview_demographics(interview)
                for quota in quotas:
                    if quota.matches(city_name, age_value, gender_value):
                        success_counts[quota.pk] += 1
                        break

            to_update: List[Quota] = []
            for quota in quotas:
                computed = success_counts.get(quota.pk, 0)
                if quota.assigned_count != computed:
                    quota.assigned_count = computed
                    to_update.append(quota)
            if to_update:
                Quota.objects.bulk_update(to_update, ['assigned_count'])

            any_city_label = _localise_text(lang, 'All cities', 'همه شهرها')
            any_age_label = _localise_text(lang, 'All ages', 'تمام سنین')
            any_gender_label = _localise_text(lang, 'Any gender', 'همه جنسیت‌ها')
            table_rows: List[Dict[str, Any]] = []
            for quota in quotas:
                assigned_value = success_counts.get(quota.pk, 0)
                table_rows.append(
                    {
                        'city': quota.city or any_city_label,
                        'age_label': quota.age_label() if quota.age_start is not None else any_age_label,
                        'gender_label': (_localise_text(lang, 'Male', 'مرد') if quota.gender == 'male' else (
                            _localise_text(lang, 'Female', 'زن') if quota.gender == 'female' else any_gender_label
                        )),
                        'target': quota.target_count,
                        'assigned': assigned_value,
                        'over': assigned_value > quota.target_count,
                    }
                )

            total = max(int(selected_project.sample_size), 1)
            if dimension_state['city']:
                city_totals: Dict[str, int] = defaultdict(int)
                for q in quotas:
                    if q.city:
                        city_totals[q.city] += q.target_count
                prefill_payload['cities'] = {
                    city: round((count * 100.0) / total, 2)
                    for city, count in city_totals.items()
                }
            if dimension_state['age']:
                age_totals: Dict[Tuple[int, int], int] = defaultdict(int)
                for q in quotas:
                    if q.age_start is not None and q.age_end is not None:
                        age_totals[(q.age_start, q.age_end)] += q.target_count
                prefill_payload['ages'] = [
                    {
                        'start': start,
                        'end': end,
                        'quota': round((count * 100.0) / total, 2),
                    }
                    for (start, end), count in sorted(age_totals.items(), key=lambda item: item[0][0])
                ]
            if dimension_state['gender']:
                gender_totals: Dict[str, int] = defaultdict(int)
                for q in quotas:
                    if q.gender:
                        gender_totals[q.gender] += q.target_count
                prefill_payload['genders'] = [
                    {
                        'value': gender_key,
                        'quota': round((count * 100.0) / total, 2),
                    }
                    for gender_key, count in gender_totals.items()
                ]

            context.update({
                'table_rows': table_rows,
            })

        context['prefill_json'] = json.dumps(prefill_payload, ensure_ascii=False)
    return render(request, 'quota_management.html', context)


@login_required
def telephone_interviewer(request: HttpRequest) -> HttpResponse:
    """Telephone interviewer panel.

    Displays a phone number to call based on the project's quota matrix and
    allows the interviewer to log the outcome of the call.  Each
    interviewer sees a unique assignment so that the same number is not
    shown twice.  When the form is submitted, a new ``Interview`` row
    is created and the corresponding quota cell's ``assigned_count``
    incremented.  The page then reloads with the next available person.
    """
    lang = request.session.get('lang', 'en')
    user = request.user
    if not _user_has_panel(user, 'telephone_interviewer'):
        messages.error(request, 'Access denied: you do not have telephone interviewer permissions.')
        return redirect('home')
    # determine accessible projects for telephone interviewer
    projects = _get_accessible_projects(user, 'telephone_interviewer')
    if not projects:
        locked = _get_locked_projects(user, panel='telephone_interviewer')
        if locked:
            locked_names = ', '.join(sorted({p.name for p in locked}))
            messages.error(
                request,
                f'Access denied: project deadlines have passed ({locked_names}). Only the owner can continue to use the telephone interviewer panel.',
            )
        else:
            messages.error(request, 'Access denied: there are no projects available for telephone interviewing.')
        return redirect('home')
    # selected project id from GET or session
    selected_project_id = request.GET.get('project') or request.session.get('telephone_project')
    selected_project = None
    person_to_call = None
    person_mobile = None
    quota_cell = None
    call_sample_obj = None
    uploaded_sample_obj = None
    prefill_age: Optional[int] = None
    prefill_birth_year: Optional[int] = None
    prefill_city: Optional[str] = None
    prefill_gender: Optional[str] = None
    quota_remaining: Dict[int, int] = {}
    sample_metadata: Dict[str, Any] = {}
    call_result_defs = resolve_call_result_definitions(None, lang)
    success_map = call_result_defs.success_map
    call_result_source_state = Project.CallResultSource.DEFAULT
    if selected_project_id:
        try:
            selected_project = Project.objects.get(pk=selected_project_id)
        except Project.DoesNotExist:
            selected_project = None
        else:
            if selected_project not in projects or _project_deadline_locked_for_user(selected_project, user):
                messages.error(
                    request,
                    'Access denied: the project deadline has passed and only the owner may use the telephone interviewer panel.',
                )
                return redirect('telephone_interviewer')
            # store selection in session for convenience
            request.session['telephone_project'] = selected_project_id
            call_result_defs = resolve_call_result_definitions(selected_project, lang)
            success_map = call_result_defs.success_map
            call_result_source_state = selected_project.call_result_source
            quota_remaining = {
                row['id']: int(row['target_count']) - int(row['assigned_count'])
                for row in Quota.objects.filter(project=selected_project).values(
                    'id', 'target_count', 'assigned_count'
                )
            }
            sample_metadata = selected_project.sample_upload_metadata or {}
            # handle POST submissions: record interview and mark sample as completed
            if request.method == 'POST':
                call_sample_id = request.POST.get('call_sample_id')
                uploaded_sample_id = request.POST.get('uploaded_sample_id')
                code_str = request.POST.get('code')
                code = int(code_str) if code_str else None
                status = success_map.get(code, False) if code is not None else False
                # parse optional fields
                gender_val = request.POST.get('gender')
                gender = boolean_from_gender_value(gender_val)
                age_input = request.POST.get('age')
                age = int(age_input) if age_input else None
                birth_year_input = request.POST.get('birth_year')
                birth_year = int(birth_year_input) if birth_year_input else None
                city_name = request.POST.get('city') or None
                # parse start_form timestamp from hidden field
                start_form_input = request.POST.get('start_form')
                start_form_dt = None
                if start_form_input:
                    try:
                        start_form_dt = datetime.fromisoformat(start_form_input)
                        if start_form_dt.tzinfo is None:
                            # If naive, assume current timezone
                            start_form_dt = timezone.make_aware(start_form_dt)
                    except Exception:
                        start_form_dt = None
                sample_source_mode = selected_project.sample_source
                call_sample = None
                posted_upload = None
                if sample_source_mode == Project.SampleSource.UPLOAD:
                    if uploaded_sample_id:
                        try:
                            posted_upload = UploadedSampleEntry.objects.get(
                                pk=uploaded_sample_id, project=selected_project
                            )
                        except UploadedSampleEntry.DoesNotExist:
                            posted_upload = None
                else:
                    if call_sample_id:
                        try:
                            call_sample = CallSample.objects.get(pk=call_sample_id)
                        except CallSample.DoesNotExist:
                            call_sample = None

                person = call_sample.person if call_sample else None
                if not city_name and posted_upload and posted_upload.city:
                    city_name = posted_upload.city
                if age is None and posted_upload and posted_upload.age is not None:
                    age = posted_upload.age
                # create interview record
                interview = Interview.objects.create(
                    project=selected_project,
                    user=user,
                    person=person,
                    status=status,
                    code=code or 0,
                    city=city_name,
                    age=age,
                    birth_year=birth_year,
                    gender=gender,
                    start_form=start_form_dt,
                    end_form=timezone.now(),
                )
                # log activity
                sample_ref = call_sample_id or (uploaded_sample_id or '')
                log_activity(
                    user,
                    'Recorded interview',
                    f"Project {selected_project.pk}, code {code}, sample {sample_ref}",
                )
                # update quota assigned count and mark sample completed
                if call_sample:
                    if status:
                        quota_obj = call_sample.quota
                        Quota.objects.filter(pk=quota_obj.pk).update(assigned_count=F('assigned_count') + 1)
                    call_sample.completed = True
                    call_sample.completed_at = timezone.now()
                    call_sample.save()
                elif posted_upload:
                    posted_upload.completed = True
                    posted_upload.completed_at = timezone.now()
                    posted_upload.save(update_fields=['completed', 'completed_at'])
                # update project's filled_samples as number of completed interviews
                selected_project.filled_samples = Interview.objects.filter(project=selected_project, status=True).count()
                selected_project.save()
                messages.success(request, 'Interview recorded.')
                # redirect back to same project to fetch next sample
                return redirect(f"{reverse('telephone_interviewer')}?project={selected_project.pk}")
            # GET: source-specific assignment logic
            if selected_project.sample_source == Project.SampleSource.UPLOAD:
                uploaded = _assign_uploaded_sample(selected_project, user)
                if uploaded:
                    uploaded_sample_obj = uploaded
                    display_name = uploaded.full_name or uploaded.phone
                    person_to_call = SimpleNamespace(full_name=display_name)
                    person_mobile = uploaded.phone
                    if uploaded.city:
                        prefill_city = uploaded.city
                    if uploaded.age is not None:
                        prefill_age = uploaded.age
                    if uploaded.gender:
                        prefill_gender = normalize_gender_value(uploaded.gender) or prefill_gender
            else:
                # First, see if the user already has a pending sample
                call_sample = (
                    CallSample.objects.filter(
                        project=selected_project, assigned_to=user, completed=False
                    )
                    .annotate(quota_remaining=F('quota__target_count') - F('quota__assigned_count'))
                    .order_by('-quota_remaining', 'assigned_at', 'pk')
                    .first()
                )
                if not call_sample:
                    call_sample = (
                        CallSample.objects.filter(
                            project=selected_project, assigned_to__isnull=True, completed=False
                        )
                        .annotate(quota_remaining=F('quota__target_count') - F('quota__assigned_count'))
                        .order_by('-quota_remaining', 'pk')
                        .first()
                    )
                    if call_sample:
                        call_sample.assigned_to = user
                        call_sample.assigned_at = timezone.now()
                        call_sample.save()
                if not call_sample:
                    try:
                        generate_call_samples(selected_project, replenish=True)
                    except Exception:
                        pass
                    call_sample = (
                        CallSample.objects.filter(
                            project=selected_project, assigned_to__isnull=True, completed=False
                        )
                        .annotate(quota_remaining=F('quota__target_count') - F('quota__assigned_count'))
                        .order_by('-quota_remaining', 'pk')
                        .first()
                    )
                    if call_sample:
                        call_sample.assigned_to = user
                        call_sample.assigned_at = timezone.now()
                        call_sample.save()
                if not call_sample:
                    try:
                        generate_call_samples(selected_project, replenish=False)
                    except Exception:
                        pass
                    call_sample = (
                        CallSample.objects.filter(
                            project=selected_project, assigned_to__isnull=True, completed=False
                        )
                        .annotate(quota_remaining=F('quota__target_count') - F('quota__assigned_count'))
                        .order_by('-quota_remaining', 'pk')
                        .first()
                    )
                    if call_sample:
                        call_sample.assigned_to = user
                        call_sample.assigned_at = timezone.now()
                        call_sample.save()
                if call_sample:
                    call_sample_obj = call_sample
                    person_to_call = call_sample.person
                    person_mobile = call_sample.mobile.mobile if call_sample.mobile else None
                    quota_cell = call_sample.quota
                    person_record = call_sample.person or (call_sample.mobile.person if call_sample.mobile else None)
                    if person_record:
                        if person_record.birth_year is not None:
                            prefill_birth_year = person_record.birth_year
                        if person_record.gender:
                            prefill_gender = normalize_gender_value(person_record.gender) or prefill_gender
                    if person_record and person_record.city_name:
                        prefill_city = person_record.city_name
                    elif call_sample.mobile and call_sample.mobile.person and call_sample.mobile.person.city_name:
                        prefill_city = call_sample.mobile.person.city_name
                    latest_interview = None
                    if person_record:
                        latest_interview = (
                            Interview.objects.filter(project=selected_project, person=person_record)
                            .order_by('-created_at')
                            .first()
                        )
                    if latest_interview:
                        if prefill_birth_year is None and latest_interview.birth_year is not None:
                            prefill_birth_year = latest_interview.birth_year
                        if prefill_city is None and latest_interview.city:
                            prefill_city = latest_interview.city
                        if latest_interview.age is not None:
                            prefill_age = latest_interview.age
                        if prefill_gender is None:
                            prefill_gender = gender_value_from_boolean(latest_interview.gender)
                    calculated_age = calculate_age_from_birth_info(prefill_birth_year, None)
                    if calculated_age is not None:
                        prefill_age = calculated_age
    # Determine start time for the interview form: if a call sample is
    # presented, record the current server time in ISO format so that the
    # template can include it as a hidden field.  This timestamp will be
    # saved to the Interview.start_form field when the form is submitted.
    start_iso = None
    if call_sample_obj or uploaded_sample_obj:
        start_iso = timezone.now().isoformat()
    context = {
        'projects': projects,
        'selected_project': selected_project,
        'person': person_to_call,
        'mobile': person_mobile,
        'quota_cell': quota_cell,
        'call_sample': call_sample_obj,
        'uploaded_sample': uploaded_sample_obj,
        'quota_remaining': quota_remaining,
        'status_codes': call_result_defs.labels,
        'start_form': start_iso,
        'prefill_age': prefill_age,
        'prefill_birth_year': prefill_birth_year,
        'prefill_city': prefill_city,
        'prefill_gender': prefill_gender,
        'sample_source': selected_project.sample_source if selected_project else Project.SampleSource.DATABASE,
        'sample_metadata': sample_metadata,
        'required_headers': SAMPLE_REQUIRED_HEADERS,
        'call_result_headers': CALL_RESULT_REQUIRED_HEADERS,
        'call_result_mode': call_result_defs.source,
        'call_result_selection': call_result_source_state,
        'lang': lang,
    }
    return render(request, 'telephone_interviewer.html', context)


@login_required
def collection_performance(request: HttpRequest) -> HttpResponse:
    """Delegate to the enhanced dashboard implementation."""

    from . import views_performance as perf

    return perf.collection_performance(request)


@login_required
def collection_performance_data(request: HttpRequest) -> JsonResponse:
    """Delegate to the enhanced JSON endpoint for chart payloads."""

    from . import views_performance as perf

    return perf.collection_performance_data(request)


@login_required
def collection_performance_export(request: HttpRequest) -> HttpResponse:
    """Delegate to the enhanced export implementation."""

    from . import views_performance as perf

    return perf.collection_performance_export(request)

# -----------------------------------------------------------------------------
# Conjoint analysis placeholder
#
# The original InsightZen implementation included a Conjoint Analysis panel
# powered by Streamlit and complex client‑side logic.  In the current
# iteration of the application, a full Django‑native implementation of that
# dashboard is not yet available.  To avoid URL resolution errors when
# upgrading an existing project that still references the ``conjoint``
# URL pattern, we provide simple stub views.  These views render the
# ``conjoint.html`` template and return a 501 JSON response for AJAX
# requests.  Organisations wishing to implement a full conjoint dashboard
# should replace these stubs with their own logic.




@login_required
def conjoint(request: HttpRequest) -> HttpResponse:
    """Display the Conjoint Analysis placeholder page.

    Users with the ``conjoint_analysis`` panel permission may load this page.
    If the user lacks permission the function redirects them to the home
    page with an error message.  The page itself simply provides a file
    upload form and a dropdown to choose the analysis type.  The underlying
    analysis functionality is not yet implemented.
    """
    if not _user_has_panel(request.user, 'conjoint_analysis'):
        messages.error(request, 'Access denied: you do not have permission to access the Conjoint Analysis panel.')
        return redirect('home')
    return render(request, 'conjoint.html')


@login_required
@require_POST
def conjoint_analyze(request: HttpRequest) -> JsonResponse:
    """Handle AJAX requests for Conjoint Analysis.

    This stub endpoint returns an HTTP 501 (Not Implemented) status to
    indicate that the analysis functionality has not yet been developed.
    Frontend scripts should handle this response gracefully and inform
    users accordingly.
    """
    if not _user_has_panel(request.user, 'conjoint_analysis'):
        return JsonResponse({'error': 'forbidden'}, status=403)
    return JsonResponse({'error': 'Conjoint Analysis is not implemented yet.'}, status=501)

# -----------------------------------------------------------------------------
# Coding analysis placeholder
#
# Similar to the Conjoint Analysis, the Coding & Category analysis panel was
# specified in earlier requirements but a full implementation is not included
# in this version of InsightZen.  To ensure the application loads without
# errors, we provide basic stub views.  These simply render the coding
# template or return a 501 response for analysis requests.

@login_required
def coding(request: HttpRequest) -> HttpResponse:
    """Display the Coding/Category analysis placeholder page.

    Users must have the ``coding`` panel permission to access this page.
    A simple form allows the user to select between coding and category
    analyses, but the underlying functionality is not yet implemented.
    """
    if not _user_has_panel(request.user, 'coding'):
        messages.error(request, 'Access denied: you do not have permission to access the Coding panel.')
        return redirect('home')
    return render(request, 'coding.html')


@login_required
@require_POST
def coding_analyze(request: HttpRequest) -> JsonResponse:
    """Handle AJAX requests for Coding & Category analysis.

    Returns a 501 status to indicate unimplemented functionality.  This
    endpoint is included solely to satisfy URL configuration and prevent
    AttributeError when the app starts.
    """
    if not _user_has_panel(request.user, 'coding'):
        return JsonResponse({'error': 'forbidden'}, status=403)
    return JsonResponse({'error': 'Coding analysis is not implemented yet.'}, status=501)


@login_required
def activity_logs(request: HttpRequest) -> HttpResponse:
    """Display activity logs for organisation users.

    This view lists recent actions recorded via ``log_activity``.  Only
    organisation users may access it.  A maximum of 500 recent log
    entries is displayed to keep the page manageable.
    """
    user = request.user
    if not _user_is_organisation(user):
        messages.error(request, 'Access denied: only organisation accounts can view logs.')
        return redirect('home')
    logs = ActivityLog.objects.select_related('user').all()[:500]
    return render(request, 'activity_logs.html', {'logs': logs})


################################################################################
# Database management views
################################################################################

@login_required
def database_list(request: HttpRequest) -> HttpResponse:
    """List database entries accessible to the current user.

    Organisation users see all entries for their projects; individual users
    only see entries for projects where they have the ``database_management``
    permission.  A disabled message is shown if the user lacks the panel.
    """
    user = request.user
    lang = _get_lang(request)
    if not _user_has_panel(user, 'database_management'):
        messages.error(request, 'Access denied: you do not have database management permissions.')
        return redirect('home')
    # Determine which projects the user can manage
    projects = _get_accessible_projects(user, panel='database_management')
    if not projects:
        locked = _get_locked_projects(user, panel='database_management')
        if locked:
            locked_names = ', '.join(sorted({p.name for p in locked}))
            messages.error(
                request,
                f'Access denied: project deadlines have passed ({locked_names}). Only the owner can continue to use the database panel.',
            )
            return redirect('home')
    entries = DatabaseEntry.objects.filter(project__in=projects).select_related('project')
    return render(
        request,
        'database_list.html',
        {
            'entries': entries,
            'lang': lang,
            'breadcrumbs': _build_breadcrumbs(
                lang,
                (_localise_text(lang, 'Databases', 'پایگاه‌های داده'), ''),
            ),
        },
    )


@login_required
def database_add(request: HttpRequest) -> HttpResponse:
    """Add a new database entry for a project.

    Presents a form for creating a ``DatabaseEntry``.  The project field
    is restricted to those projects where the current user has the
    ``database_management`` permission.  On success, the entry is saved
    with ``status`` initially False.  A background sync (not implemented
    here) can subsequently update the status.
    """
    user = request.user
    lang = _get_lang(request)
    if not _user_has_panel(user, 'database_management'):
        messages.error(request, 'Access denied: you do not have permission to add databases.')
        return redirect('home')
    projects = _get_accessible_projects(user, panel='database_management')
    if not projects:
        locked = _get_locked_projects(user, panel='database_management')
        if locked:
            locked_names = ', '.join(sorted({p.name for p in locked}))
            messages.error(
                request,
                f'Access denied: project deadlines have passed ({locked_names}). Only the owner can continue to use the database panel.',
            )
        else:
            messages.error(request, 'Access denied: you do not have a project available for database management.')
        return redirect('home')
    if request.method == 'POST':
        form = DatabaseEntryForm(request.POST)
        form.fields['project'].queryset = Project.objects.filter(pk__in=[p.pk for p in projects])
        if form.is_valid():
            entry: DatabaseEntry = form.save(commit=False)
            entry.status = False
            entry.last_sync = None
            entry.last_error = ''
            entry.save()
            entry.last_update_requested = timezone.now()
            entry.save(update_fields=['last_update_requested'])
            sync_message = ''
            try:
                result = refresh_entry_cache(entry)
                entry.status = True
                entry.last_error = ''
                sync_message = f" Cached {result.total} records."
            except DatabaseCacheError as exc:
                entry.status = False
                entry.last_error = str(exc)
                messages.warning(request, f'Initial sync failed: {exc}')
            now = timezone.now()
            entry.last_sync = now
            if entry.status:
                entry.last_manual_update = now
            entry.save(update_fields=['status', 'last_error', 'last_sync', 'last_manual_update'])
            success_message = 'Database entry created successfully.'
            if sync_message:
                success_message += sync_message
            messages.success(request, success_message)
            # Trigger background sync here if desired (e.g. Celery, management command)
            log_activity(user, 'Added database entry', f"DB {entry.db_name} for Project {entry.project.pk}")
            return redirect('database_list')
    else:
        form = DatabaseEntryForm()
        form.fields['project'].queryset = Project.objects.filter(pk__in=[p.pk for p in projects])
    return render(
        request,
        'database_form.html',
        {
            'form': form,
            'title': _localise_text(lang, 'Add Database', 'افزودن پایگاه داده'),
            'lang': lang,
            'is_create': True,
            'breadcrumbs': _build_breadcrumbs(
                lang,
                (
                    _localise_text(lang, 'Databases', 'پایگاه‌های داده'),
                    reverse('database_list'),
                ),
                (_localise_text(lang, 'Add database', 'افزودن پایگاه'), ''),
            ),
        },
    )


@login_required
def database_edit(request: HttpRequest, pk: int) -> HttpResponse:
    """Edit an existing database entry.

    Only users with the ``database_management`` permission for the
    associated project may edit the entry.  On POST the entry is
    updated.  The status field is not editable here; it will be
    updated by background sync logic.
    """
    user = request.user
    lang = _get_lang(request)
    if not _user_has_panel(user, 'database_management'):
        messages.error(request, 'Access denied: you do not have permission to edit databases.')
        return redirect('home')
    entry = get_object_or_404(DatabaseEntry, pk=pk)
    projects = _get_accessible_projects(user, panel='database_management')
    if entry.project not in projects:
        messages.error(request, 'You do not have permission to edit this database.')
        return redirect('database_list')
    if not _ensure_project_deadline_access(request, entry.project):
        return redirect('database_list')
    if request.method == 'POST':
        form = DatabaseEntryForm(request.POST, instance=entry)
        form.fields['project'].queryset = Project.objects.filter(pk__in=[p.pk for p in projects])
        if form.is_valid():
            entry = form.save()
            entry.last_update_requested = timezone.now()
            entry.save(update_fields=['last_update_requested'])
            sync_message = ''
            try:
                result = refresh_entry_cache(entry)
                entry.status = True
                entry.last_error = ''
                sync_message = f" Cached {result.total} records."
            except DatabaseCacheError as exc:
                entry.status = False
                entry.last_error = str(exc)
                messages.warning(request, f'Sync failed after update: {exc}')
            now = timezone.now()
            entry.last_sync = now
            if entry.status:
                entry.last_manual_update = now
            entry.save(update_fields=['status', 'last_error', 'last_sync', 'last_manual_update'])
            success_message = 'Database entry updated successfully.'
            if sync_message:
                success_message += sync_message
            messages.success(request, success_message)
            log_activity(user, 'Edited database entry', f"DB {entry.db_name} for Project {entry.project.pk}")
            return redirect('database_list')
    else:
        form = DatabaseEntryForm(instance=entry)
        form.fields['project'].queryset = Project.objects.filter(pk__in=[p.pk for p in projects])
    return render(
        request,
        'database_form.html',
        {
            'form': form,
            'title': _localise_text(lang, 'Edit Database', 'ویرایش پایگاه داده'),
            'lang': lang,
            'is_create': False,
            'breadcrumbs': _build_breadcrumbs(
                lang,
                (
                    _localise_text(lang, 'Databases', 'پایگاه‌های داده'),
                    reverse('database_list'),
                ),
                (
                    _localise_text(lang, 'Edit database', 'ویرایش پایگاه'),
                    '',
                ),
            ),
        },
    )


@login_required
@require_POST
def database_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete a database entry and its associated data table.

    If the user has permission to manage this entry's project, the
    entry is removed and the corresponding PostgreSQL table (named
    after the entry's asset_id) is dropped.  Failures during table
    deletion are silently ignored.
    """
    user = request.user
    if not _user_has_panel(user, 'database_management'):
        messages.error(request, 'Access denied: you do not have permission to delete databases.')
        return redirect('home')
    entry = get_object_or_404(DatabaseEntry, pk=pk)
    projects = _get_accessible_projects(user, panel='database_management')
    if entry.project not in projects:
        messages.error(request, 'You do not have permission to delete this database.')
        return redirect('database_list')
    if not _ensure_project_deadline_access(request, entry.project):
        return redirect('database_list')
    # Attempt to drop the table corresponding to this entry
    try:
        # Build a connection to the default database configured in settings
        db_conf = settings.DATABASES.get('default', {})
        conn = psycopg2.connect(
            host=db_conf.get('HOST', '127.0.0.1'),
            port=db_conf.get('PORT', 5432),
            dbname=db_conf.get('NAME'),
            user=db_conf.get('USER'),
            password=db_conf.get('PASSWORD'),
        )
        table_name = _sanitize_identifier(entry.asset_id)
        with conn.cursor() as cur:
            cur.execute(sql.SQL("DROP TABLE IF EXISTS {} CASCADE;").format(sql.Identifier(table_name)))
        conn.commit()
        conn.close()
    except Exception:
        # Fail silently; deletion of the Django record should still proceed
        pass
    delete_entry_cache(entry)
    entry.delete()
    messages.success(request, 'Database entry deleted successfully.')
    log_activity(user, 'Deleted database entry', f"DB {entry.db_name} for Project {entry.project.pk}")
    return redirect('database_list')


@login_required
@require_POST
def database_update(request: HttpRequest, pk: int) -> HttpResponse:
    """Trigger an incremental cache refresh for a ``DatabaseEntry``.

    Users may invoke this action from the database list to fetch new Kobo
    submissions.  To prevent abuse, each entry is limited to ten manual
    refreshes within a rolling 90 minute window.
    """

    user = request.user
    if not _user_has_panel(user, 'database_management'):
        messages.error(request, 'Access denied: you do not have permission to update databases.')
        return redirect('home')

    entry = get_object_or_404(DatabaseEntry, pk=pk)
    projects = _get_accessible_projects(user, panel='database_management')
    if entry.project not in projects:
        messages.error(request, 'You do not have permission to update this database.')
        return redirect('database_list')
    if not _ensure_project_deadline_access(request, entry.project):
        return redirect('database_list')

    now = timezone.now()
    window_start = entry.update_window_start
    if window_start is None or now - window_start >= timedelta(minutes=90):
        entry.update_window_start = now
        entry.update_attempt_count = 0
    elif entry.update_attempt_count >= 10:
        retry_at = entry.update_window_start + timedelta(minutes=90)
        wait_seconds = max(int((retry_at - now).total_seconds()), 0)
        wait_minutes = (wait_seconds + 59) // 60
        if wait_minutes <= 0:
            wait_message = 'Update limit reached. Please try again shortly.'
        else:
            wait_message = (
                'Update limit reached. Please try again in about '
                f"{wait_minutes} minute{'s' if wait_minutes != 1 else ''}."
            )
        messages.warning(request, wait_message)
        return redirect('database_list')

    entry.update_attempt_count += 1
    entry.last_update_requested = now
    entry.save(update_fields=['update_window_start', 'update_attempt_count', 'last_update_requested'])

    tracked_window_start = timezone.now() - timedelta(days=30)
    tracked_qs = list(DatabaseEntryEditRequest.objects.filter(entry=entry, requested_at__gte=tracked_window_start))
    tracked_ids = [req.submission_id for req in tracked_qs]

    try:
        result = refresh_entry_cache(entry, refresh_ids=tracked_ids)
        entry.status = True
        entry.last_error = ''
        entry.last_manual_update = now
        entry.last_sync = now
        entry.save(update_fields=['status', 'last_error', 'last_manual_update', 'last_sync'])
        messages.success(
            request,
            (
                'Database updated successfully. '
                f"Added {result.added} and updated {result.updated} submissions (total {result.total})."
            ),
        )
        # Remove any tracked edit requests outside the rolling window to keep the
        # cache tidy once their refreshed versions have been downloaded.
        DatabaseEntryEditRequest.objects.filter(entry=entry, requested_at__lt=tracked_window_start).delete()
        log_activity(user, 'Manually updated database entry', f"DB {entry.db_name} for Project {entry.project.pk}")
    except DatabaseCacheError as exc:
        entry.status = False
        entry.last_error = str(exc)
        entry.last_sync = now
        entry.save(update_fields=['status', 'last_error', 'last_sync'])
        messages.error(request, f'Failed to update database: {exc}')
        log_activity(user, 'Failed database update', f"DB {entry.db_name} for Project {entry.project.pk}")

    return redirect('database_list')


@login_required
def database_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Display cached Kobo submissions for a database entry.

    This view reads the JSON snapshot produced during synchronisation for
    the given ``DatabaseEntry`` and paginates the cached submissions so
    operators can browse the payload in manageable slices. Only users with
    the ``database_management`` permission for the associated project may
    view the cached data.
    """
    user = request.user
    if not _user_has_panel(user, 'database_management'):
        messages.error(request, 'Access denied: you do not have permission to view databases.')
        return redirect('home')
    entry = get_object_or_404(DatabaseEntry, pk=pk)
    projects = _get_accessible_projects(user, panel='database_management')
    if entry.project not in projects:
        messages.error(request, 'You do not have permission to view this database.')
        return redirect('database_list')
    if not _ensure_project_deadline_access(request, entry.project):
        return redirect('database_list')
    snapshot = load_entry_snapshot(entry)
    all_records = snapshot.records
    # NOTE: For very large payloads we may need to stream or cache slices client-side
    # to avoid loading the full JSON into memory during rendering.
    total_records = len(all_records)
    page_sizes = [5, 30, 50, 200]
    default_page_size = page_sizes[0]
    try:
        requested_size = int(request.GET.get('page_size', default_page_size))
    except (TypeError, ValueError):
        requested_size = default_page_size
    page_size = requested_size if requested_size in page_sizes else default_page_size
    total_pages = max(1, ceil(total_records / page_size))
    try:
        requested_page = int(request.GET.get('page', 1))
    except (TypeError, ValueError):
        requested_page = 1
    page = min(max(1, requested_page), total_pages)
    start = (page - 1) * page_size
    end = start + page_size
    records = all_records[start:end]
    columns = infer_columns(all_records)
    rows: List[List[Any]] = []
    for record in records:
        row: List[Any] = []
        for column in columns:
            value = record.get(column)
            if isinstance(value, (dict, list)):
                row.append(json.dumps(value, ensure_ascii=False))
            elif value is None:
                row.append('')
            else:
                row.append(value)
        rows.append(row)
    return render(request, 'database_view.html', {
        'entry': entry,
        'columns': columns,
        'rows': rows,
        'snapshot': snapshot,
        'page': page,
        'page_size': page_size,
        'page_sizes': page_sizes,
        'total_pages': total_pages,
        'total_records': total_records,
        'start_index': start + 1 if total_records else 0,
        'end_index': min(end, total_records),
        'has_previous': page > 1,
        'has_next': page < total_pages,
    })


@login_required
def qc_edit(request: HttpRequest) -> HttpResponse:
    """Data quality control dashboard backed by cached Kobo submissions."""

    user = request.user
    lang = request.session.get('lang', 'en')
    if not (
        _user_has_panel(user, 'qc_management')
        or _user_has_panel(user, 'qc_performance')
        or _user_has_panel(user, 'edit_data')
    ):
        messages.error(request, 'Access denied: you do not have quality control permissions.')
        return redirect('home')

    project_qs = Project.objects.filter(memberships__user=user)
    if not _user_is_organisation(user):
        project_qs = project_qs.filter(
            Q(memberships__qc_management=True)
            | Q(memberships__qc_performance=True)
            | Q(memberships__edit_data=True)
        )
    accessible_projects = list(project_qs.distinct().order_by('name'))

    selected_project: Optional[Project] = None
    selected_entry: Optional[DatabaseEntry] = None
    entries_for_project: List[DatabaseEntry] = []
    snapshot = None
    columns: List[str] = []
    column_meta: List[Dict[str, Any]] = []
    filter_values: List[Dict[str, Any]] = []
    table_rows: List[Dict[str, Any]] = []
    tracked_requests: List[DatabaseEntryEditRequest] = []

    project_param = request.GET.get('project')
    if project_param:
        for project in accessible_projects:
            if str(project.pk) == project_param:
                selected_project = project
                break

    if selected_project:
        entries_for_project = list(DatabaseEntry.objects.filter(project=selected_project).order_by('db_name'))
        entry_param = request.GET.get('entry')
        if entry_param:
            for entry in entries_for_project:
                if str(entry.pk) == entry_param:
                    selected_entry = entry
                    break

    search_term = (request.GET.get('search') or '').strip()
    column_filters: Dict[str, str] = {}
    page_sizes = [5, 30, 50, 200]
    default_page_size = 5
    page_size = default_page_size
    page = 1
    total_pages = 1
    total_records = 0
    start_index = 0
    end_index = 0
    has_previous = False
    has_next = False

    if selected_entry:
        snapshot = load_entry_snapshot(selected_entry)
        records = snapshot.records
        columns = infer_columns(records)
        for idx, column in enumerate(columns):
            value = (request.GET.get(f'filter_{idx}') or '').strip()
            filter_values.append({'index': idx, 'name': column, 'value': value})
            if value:
                column_filters[column] = value
            column_meta.append({'index': idx, 'name': column, 'sort_type': _detect_sort_type(records, column)})

        search_terms = [term for term in search_term.lower().split() if term]
        filtered_records: List[Tuple[Dict[str, Any], Dict[str, str]]] = []
        for record in records:
            value_map = {col: _normalise_record_value(record.get(col)) for col in columns}
            combined_text = ' '.join(value_map.values()).lower()
            if search_terms and not all(term in combined_text for term in search_terms):
                continue
            matches = True
            for col, filter_text in column_filters.items():
                if not _matches_filter_value(value_map[col], filter_text):
                    matches = False
                    break
            if matches:
                filtered_records.append((record, value_map))

        total_records = len(filtered_records)
        try:
            requested_size = int(request.GET.get('page_size', default_page_size))
        except (TypeError, ValueError):
            requested_size = default_page_size
        if requested_size in page_sizes:
            page_size = requested_size
        total_pages = max(1, ceil(total_records / page_size))
        try:
            requested_page = int(request.GET.get('page', 1))
        except (TypeError, ValueError):
            requested_page = 1
        page = min(max(1, requested_page), total_pages)
        start_index = (page - 1) * page_size
        end_index = min(start_index + page_size, total_records)
        has_previous = page > 1
        has_next = page < total_pages
        page_slice = filtered_records[start_index:end_index]

        tracked_since = timezone.now() - timedelta(days=30)
        tracked_requests = list(
            DatabaseEntryEditRequest.objects.filter(entry=selected_entry, requested_at__gte=tracked_since)
        )
        tracked_ids = {req.submission_id for req in tracked_requests}

        for record, value_map in page_slice:
            submission_id = _extract_submission_id(record)
            table_rows.append({
                'values': [value_map[col] for col in columns],
                'submission_id': submission_id,
                'is_tracked': submission_id in tracked_ids,
            })

    context = {
        'projects': accessible_projects,
        'selected_project': selected_project,
        'entries': entries_for_project,
        'selected_entry': selected_entry,
        'snapshot': snapshot,
        'columns': columns,
        'column_meta': column_meta,
        'filter_values': filter_values,
        'table_rows': table_rows,
        'search_term': search_term,
        'page': page,
        'page_size': page_size,
        'page_sizes': page_sizes,
        'total_pages': total_pages,
        'total_records': total_records,
        'start_index': start_index + 1 if total_records else 0,
        'end_index': end_index,
        'has_previous': has_previous,
        'has_next': has_next,
        'tracked_requests': tracked_requests,
        'lang': lang,
    }
    return render(request, 'qc_edit.html', context)


@login_required
@require_POST
def qc_edit_link(request: HttpRequest, entry_id: int) -> JsonResponse:
    """Return an Enketo edit link for a given submission."""

    user = request.user
    entry = get_object_or_404(DatabaseEntry, pk=entry_id)
    project = entry.project
    lang = request.session.get('lang', 'en')
    if not (
        _user_is_organisation(user)
        or Membership.objects.filter(
            user=user,
            project=project,
        )
        .filter(Q(qc_management=True) | Q(qc_performance=True) | Q(edit_data=True))
        .exists()
    ):
        message = 'Access denied.' if lang != 'fa' else 'دسترسی مجاز نیست.'
        return JsonResponse({'error': message}, status=403)

    try:
        payload = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        payload = {}
    submission_id = str(payload.get('submission_id') or request.POST.get('submission_id') or '').strip()
    if not submission_id:
        message = 'Submission id is required.' if lang != 'fa' else 'شناسه ارسال لازم است.'
        return JsonResponse({'error': message}, status=400)

    tracked_window_start = timezone.now() - timedelta(days=30)
    DatabaseEntryEditRequest.objects.filter(entry=entry, requested_at__lt=tracked_window_start).delete()

    return_url = request.build_absolute_uri(
        f"{reverse('qc_edit')}?project={project.pk}&entry={entry.pk}"
    )
    try:
        edit_url = request_enketo_edit_url(entry, submission_id, return_url=return_url)
    except EnketoLinkError as exc:
        return JsonResponse({'error': str(exc)}, status=502)

    DatabaseEntryEditRequest.objects.update_or_create(
        entry=entry,
        submission_id=submission_id,
        defaults={'requested_at': timezone.now()},
    )

    return JsonResponse({'url': edit_url})


def _localise_message(lang: str, english: str, persian: str) -> str:
    """Return a message in the user's preferred language."""

    return persian if lang == 'fa' else english


def _serialise_filter_preset(preset: TableFilterPreset) -> Dict[str, Any]:
    """Convert a ``TableFilterPreset`` into a JSON-safe dictionary."""

    return {
        'name': preset.name,
        'table_id': preset.table_id,
        'payload': preset.payload,
        'created_at': preset.created_at.isoformat(),
        'updated_at': preset.updated_at.isoformat(),
    }


@login_required
@require_http_methods(["GET", "POST", "DELETE"])
def table_filter_presets(request: HttpRequest, table_id: str) -> JsonResponse:
    """Create, list or delete saved advanced-filter presets for a table."""

    lang = request.session.get('lang', 'en')
    table_id = (table_id or '').strip()
    if not table_id or not _TABLE_ID_PATTERN.match(table_id):
        message = _localise_message(
            lang,
            'Invalid table identifier.',
            'شناسه جدول نامعتبر است.',
        )
        return JsonResponse({'error': message}, status=400)

    if request.method == 'GET':
        presets = TableFilterPreset.objects.filter(user=request.user, table_id=table_id).order_by('name')
        return JsonResponse({'presets': [_serialise_filter_preset(p) for p in presets]})

    try:
        payload = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        message = _localise_message(
            lang,
            'Invalid JSON payload.',
            'دادهٔ ارسال شده معتبر نیست.',
        )
        return JsonResponse({'error': message}, status=400)

    name = str(payload.get('name') or '').strip()
    if not name:
        message = _localise_message(
            lang,
            'A name is required to save filters.',
            'برای ذخیره فیلتر لازم است نامی وارد کنید.',
        )
        return JsonResponse({'error': message}, status=400)

    preset_payload = payload.get('payload') or {}
    logic = 'or' if preset_payload.get('logic') == 'or' else 'and'
    raw_filters = preset_payload.get('filters') or []
    if not isinstance(raw_filters, list):
        raw_filters = []

    normalised_filters: List[Dict[str, Any]] = []
    for item in raw_filters:
        try:
            column = int(item.get('column'))
        except (TypeError, ValueError):
            continue
        operator = str(item.get('operator') or '').strip()
        if not operator:
            continue
        values = item.get('values') or []
        if not isinstance(values, list):
            values = []
        normalised_values = [str(value) for value in values]
        condition_type = str(item.get('type') or 'text').strip() or 'text'
        normalised_filters.append(
            {
                'column': column,
                'operator': operator,
                'values': normalised_values,
                'type': condition_type,
            }
        )

    if request.method == 'DELETE':
        deleted, _ = TableFilterPreset.objects.filter(
            user=request.user,
            table_id=table_id,
            name=name,
        ).delete()
        if deleted:
            message = _localise_message(
                lang,
                'Filter removed.',
                'فیلتر حذف شد.',
            )
            remaining = TableFilterPreset.objects.filter(user=request.user, table_id=table_id).order_by('name')
            return JsonResponse({'presets': [_serialise_filter_preset(p) for p in remaining], 'message': message})
        message = _localise_message(
            lang,
            'Filter not found.',
            'فیلتر مورد نظر یافت نشد.',
        )
        return JsonResponse({'error': message}, status=404)

    if not normalised_filters:
        message = _localise_message(
            lang,
            'At least one condition is required to save a preset.',
            'برای ذخیره فیلتر باید حداقل یک شرط تعیین کنید.',
        )
        return JsonResponse({'error': message}, status=400)

    version = preset_payload.get('version')
    try:
        version = int(version)
    except (TypeError, ValueError):
        version = 1

    context_label = str(preset_payload.get('context') or '').strip()
    if context_label:
        context_label = context_label[:150]

    columns_meta = []
    raw_columns = preset_payload.get('columns')
    if isinstance(raw_columns, list):
        for column_meta in raw_columns:
            try:
                meta_index = int(column_meta.get('index'))
            except (TypeError, ValueError, AttributeError):
                continue
            meta_name = str(column_meta.get('name') or '').strip()
            meta_type = str(column_meta.get('type') or '').strip() or 'text'
            columns_meta.append({'index': meta_index, 'name': meta_name, 'type': meta_type})

    normalised_payload = {
        'version': version,
        'logic': logic,
        'filters': normalised_filters,
    }
    if context_label:
        normalised_payload['context'] = context_label
    if columns_meta:
        normalised_payload['columns'] = columns_meta

    preset, _ = TableFilterPreset.objects.update_or_create(
        user=request.user,
        table_id=table_id,
        name=name,
        defaults={'payload': normalised_payload},
    )

    message = _localise_message(
        lang,
        'Filter saved successfully.',
        'فیلتر با موفقیت ذخیره شد.',
    )
    updated = TableFilterPreset.objects.filter(user=request.user, table_id=table_id).order_by('name')
    return JsonResponse(
        {
            'preset': _serialise_filter_preset(preset),
            'presets': [_serialise_filter_preset(p) for p in updated],
            'message': message,
        }
    )


@login_required
@require_http_methods(["GET"])
def notifications_unread(request: HttpRequest) -> JsonResponse:
    """Return unread notifications for the current user."""

    lang = request.session.get('lang', 'en')
    lang = 'fa' if lang == 'fa' else 'en'
    unread_qs = Notification.objects.filter(recipient=request.user, is_read=False).order_by('-created_at')
    total = unread_qs.count()
    items: List[Dict[str, Any]] = []
    for note in unread_qs[:50]:
        items.append(
            {
                'id': note.pk,
                'message': localised_message(note, lang),
                'eventType': note.event_type,
                'createdAt': note.created_at.isoformat(),
                'project': note.project.name if note.project else None,
                'metadata': note.metadata,
            }
        )
    return JsonResponse({'notifications': items, 'count': total})


@login_required
@require_http_methods(["POST"])
def notifications_mark_read(request: HttpRequest) -> JsonResponse:
    """Mark notifications as read for the current user."""

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'ok': False, 'message': 'Invalid payload.'}, status=400)

    if payload.get('all'):
        updated = mark_notifications_read(request.user, None)
    else:
        ids = payload.get('ids')
        if not isinstance(ids, list):
            return JsonResponse({'ok': False, 'message': 'No notifications specified.'}, status=400)
        try:
            id_list = [int(value) for value in ids]
        except (TypeError, ValueError):
            return JsonResponse({'ok': False, 'message': 'Invalid notification identifiers.'}, status=400)
        updated = mark_notifications_read(request.user, id_list)

    return JsonResponse({'ok': True, 'updated': updated})


def _calendar_user_label(user: User) -> str:
    return user.get_full_name() or user.first_name or user.username


def _calendar_participants_queryset(user: User):
    if _user_is_organisation(user):
        return User.objects.all()
    project_ids = list(Membership.objects.filter(user=user).values_list('project_id', flat=True))
    if not project_ids:
        return User.objects.filter(pk=user.pk)
    return User.objects.filter(Q(pk=user.pk) | Q(memberships__project_id__in=project_ids)).distinct()


def _calendar_event_queryset(user: User):
    return CalendarEvent.objects.filter(Q(created_by=user) | Q(participants=user)).distinct()


def _serialise_calendar_event(event: CalendarEvent, viewer: User) -> Dict[str, Any]:
    participants = [
        {
            'id': participant.pk,
            'name': _calendar_user_label(participant),
            'email': participant.email,
        }
        for participant in event.participants.all()
    ]
    creator_label = _calendar_user_label(event.created_by)
    return {
        'id': event.pk,
        'title': event.title,
        'description': event.description,
        'start': event.start.isoformat(),
        'end': event.end.isoformat(),
        'reminder_minutes_before': event.reminder_minutes_before,
        'participants': participants,
        'creator': {'id': event.created_by_id, 'name': creator_label},
        'can_edit': event.created_by_id == viewer.pk,
    }


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed


def _load_json_body(request: HttpRequest) -> Dict[str, Any] | None:
    try:
        return json.loads(request.body.decode('utf-8') or '{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _dispatch_calendar_reminders() -> None:
    now = timezone.now()
    upcoming = CalendarEvent.objects.filter(
        reminder_minutes_before__isnull=False,
        reminder_sent=False,
        start__gte=now - timedelta(days=1),
    ).select_related('created_by').prefetch_related('participants')
    for event in upcoming:
        minutes = event.reminder_minutes_before or 0
        if minutes <= 0:
            continue
        reminder_time = event.start - timedelta(minutes=minutes)
        if reminder_time > now:
            continue
        recipients: List[User] = list(event.participants.all())
        if event.created_by not in recipients:
            recipients.append(event.created_by)
        notify_event_reminder(event, recipients)
        event.reminder_sent = True
        event.save(update_fields=['reminder_sent'])


@login_required
@require_http_methods(["GET"])
def calendar_participants(request: HttpRequest) -> JsonResponse:
    qs = _calendar_participants_queryset(request.user).order_by('first_name', 'username')
    data = [
        {'id': user.pk, 'name': _calendar_user_label(user), 'email': user.email}
        for user in qs
    ]
    return JsonResponse({'participants': data})


def _clean_event_payload(payload: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], Optional[datetime], Optional[datetime], Optional[int], List[int]]:
    title = str(payload.get('title') or '').strip()
    description = str(payload.get('description') or '').strip()
    start_dt = _parse_iso_datetime(payload.get('start'))
    end_dt = _parse_iso_datetime(payload.get('end'))
    reminder = payload.get('reminder_minutes_before')
    reminder_val: Optional[int] = None
    if reminder not in (None, ''):
        try:
            reminder_val = max(0, int(reminder))
        except (TypeError, ValueError):
            reminder_val = None
    participants = payload.get('participants') or []
    participant_ids: List[int] = []
    if isinstance(participants, list):
        for pid in participants:
            try:
                participant_ids.append(int(pid))
            except (TypeError, ValueError):
                continue
    return title, description, start_dt, end_dt, reminder_val, participant_ids


@login_required
@require_http_methods(["GET", "POST"])
def calendar_events(request: HttpRequest) -> JsonResponse:
    _dispatch_calendar_reminders()
    if request.method == 'GET':
        start_dt = _parse_iso_datetime(request.GET.get('start'))
        end_dt = _parse_iso_datetime(request.GET.get('end'))
        qs = _calendar_event_queryset(request.user).select_related('created_by').prefetch_related('participants')
        if start_dt and end_dt:
            qs = qs.filter(start__lt=end_dt, end__gt=start_dt)
        events = [_serialise_calendar_event(event, request.user) for event in qs]
        return JsonResponse({'events': events})

    payload = _load_json_body(request)
    if payload is None:
        return JsonResponse({'ok': False, 'message': 'Invalid payload.'}, status=400)
    title, description, start_dt, end_dt, reminder_val, participant_ids = _clean_event_payload(payload)
    if not title or not start_dt or not end_dt:
        return JsonResponse({'ok': False, 'message': 'Missing required fields.'}, status=400)
    if end_dt <= start_dt:
        return JsonResponse({'ok': False, 'message': 'End time must be after start time.'}, status=400)

    allowed_ids = set(_calendar_participants_queryset(request.user).values_list('pk', flat=True))
    selected_ids = [pid for pid in participant_ids if pid in allowed_ids and pid != request.user.pk]

    event = CalendarEvent.objects.create(
        title=title,
        description=description,
        start=start_dt,
        end=end_dt,
        reminder_minutes_before=reminder_val,
        created_by=request.user,
    )
    participant_users = list(User.objects.filter(pk__in=selected_ids))
    if request.user not in participant_users:
        participant_users.append(request.user)
    event.participants.set(participant_users)
    log_activity(request.user, 'Created calendar event', f'Event {event.pk}: {event.title}')
    notify_event_invite(event, [user for user in participant_users if user != request.user], actor=request.user)

    data = _serialise_calendar_event(event, request.user)
    return JsonResponse({'ok': True, 'event': data})


@login_required
@require_http_methods(["GET", "PUT", "PATCH", "DELETE"])
def calendar_event_detail(request: HttpRequest, event_id: int) -> JsonResponse:
    _dispatch_calendar_reminders()
    event = get_object_or_404(
        _calendar_event_queryset(request.user).select_related('created_by').prefetch_related('participants'),
        pk=event_id,
    )
    if request.method == 'GET':
        return JsonResponse({'event': _serialise_calendar_event(event, request.user)})
    if request.method == 'DELETE':
        if event.created_by != request.user:
            return JsonResponse({'ok': False, 'message': 'Only the event owner can delete this item.'}, status=403)
        event.delete()
        log_activity(request.user, 'Deleted calendar event', f'Event {event_id}')
        return JsonResponse({'ok': True})

    if event.created_by != request.user:
        return JsonResponse({'ok': False, 'message': 'Only the event owner can update this item.'}, status=403)
    payload = _load_json_body(request)
    if payload is None:
        return JsonResponse({'ok': False, 'message': 'Invalid payload.'}, status=400)

    title, description, start_dt, end_dt, reminder_val, participant_ids = _clean_event_payload(payload)
    if not title or not start_dt or not end_dt:
        return JsonResponse({'ok': False, 'message': 'Missing required fields.'}, status=400)
    if end_dt <= start_dt:
        return JsonResponse({'ok': False, 'message': 'End time must be after start time.'}, status=400)

    allowed_ids = set(_calendar_participants_queryset(request.user).values_list('pk', flat=True))
    selected_ids = [pid for pid in participant_ids if pid in allowed_ids and pid != request.user.pk]
    participant_users = list(User.objects.filter(pk__in=selected_ids))
    if request.user not in participant_users:
        participant_users.append(request.user)

    fields_to_update = []
    if event.title != title:
        event.title = title
        fields_to_update.append('title')
    if event.description != description:
        event.description = description
        fields_to_update.append('description')
    if event.start != start_dt:
        event.start = start_dt
        fields_to_update.append('start')
        event.reminder_sent = False
    if event.end != end_dt:
        event.end = end_dt
        fields_to_update.append('end')
    if event.reminder_minutes_before != reminder_val:
        event.reminder_minutes_before = reminder_val
        fields_to_update.append('reminder_minutes_before')
        event.reminder_sent = False
    if fields_to_update:
        fields_to_update.append('reminder_sent')
        event.save(update_fields=list(set(fields_to_update)))
    event.participants.set(participant_users)
    log_activity(request.user, 'Updated calendar event', f'Event {event.pk}')
    notify_event_update(event, [user for user in participant_users if user != request.user], actor=request.user)

    return JsonResponse({'ok': True, 'event': _serialise_calendar_event(event, request.user)})
