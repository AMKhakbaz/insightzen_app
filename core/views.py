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
from datetime import datetime, timedelta
from math import ceil
from typing import Any, Dict, Iterable, List, Tuple, Optional

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Sum, Count, Q, F
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.utils import timezone
import random
import re
import psycopg2
from psycopg2 import sql  # type: ignore
from django.conf import settings

from core.services.database_cache import (
    DatabaseCacheError,
    EnketoLinkError,
    delete_entry_cache,
    infer_columns,
    load_entry_snapshot,
    refresh_entry_cache,
    request_enketo_edit_url,
)
try:
    # Optional import for Excel export; if the library is missing the export view
    # will inform the user appropriately.
    import openpyxl  # type: ignore
    from openpyxl.chart import BarChart, Reference  # type: ignore
except Exception:
    openpyxl = None  # type: ignore

from .forms import (
    LoginForm,
    ProjectForm,
    RegistrationForm,
    UserToProjectForm,
    DatabaseEntryForm,
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
    DatabaseEntry,
    DatabaseEntryEditRequest,
)


def register(request: HttpRequest) -> HttpResponse:
    """Handle user registration.

    When the submitted form indicates an organisation registration, the
    partially completed user data is stored in the session and the user is
    redirected to a mock payment page.  Otherwise the user and their
    profile are immediately created and the user is sent to the login page.
    """
    if request.user.is_authenticated:
        return redirect('home')
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
    return render(request, 'register.html', {'form': form})


def payment(request: HttpRequest) -> HttpResponse:
    """Simulate a payment gateway for organisation registrations."""
    pending = request.session.get('pending_registration')
    if not pending:
        return redirect('register')
    if request.method == 'POST':
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
    return render(request, 'payment.html')


def login_view(request: HttpRequest) -> HttpResponse:
    """Authenticate a user via email and password."""
    if request.user.is_authenticated:
        return redirect('home')
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
    return render(request, 'login.html', {'form': form})


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
    return render(request, 'home.html', {'profile': profile})


def _user_is_organisation(user: User) -> bool:
    profile = getattr(user, 'profile', None)
    return bool(profile and profile.organization)


def _user_has_panel(user: User, panel: str) -> bool:
    """Check whether a non‑organisation user has access to a panel.

    Organisation users automatically have access to all panels.
    """
    if _user_is_organisation(user):
        return True
    return any(getattr(m, panel) for m in user.memberships.all())


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
    quotas = Quota.objects.filter(project=project).order_by('city', 'age_start', 'age_end')
    if not replenish:
        # Clear existing samples when regenerating from scratch
        CallSample.objects.filter(project=project).delete()
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
        desired = max(int(q.target_count) * 3, 0)
        existing_open = CallSample.objects.filter(project=project, quota=q, completed=False).count()
        if replenish:
            to_create = max(desired - existing_open, 0)
        else:
            to_create = desired
        if to_create <= 0:
            continue
        # compute birth year range from age range
        birth_min = current_year - int(q.age_end)
        birth_max = current_year - int(q.age_start)
        # Primary candidate set: matching city and age range
        base_qs = (
            Person.objects.filter(
                city_name=q.city,
                birth_year__gte=birth_min,
                birth_year__lte=birth_max,
                mobiles__isnull=False,
            )
            .exclude(mobiles__mobile__in=exclude_mobiles)
            .distinct()
        )
        candidates: List[str] = list(base_qs.values_list('national_code', flat=True)[: to_create * 8])
        # Fallback 1: same city without age filtering
        if len(candidates) < to_create:
            fb1 = (
                Person.objects.filter(city_name=q.city, mobiles__isnull=False)
                .exclude(mobiles__mobile__in=exclude_mobiles)
                .exclude(national_code__in=candidates)
                .distinct()
                .values_list('national_code', flat=True)[: (to_create * 8)]
            )
            candidates = list(set(candidates) | set(fb1))
        # Fallback 2: any city and any age
        if len(candidates) < to_create:
            fb2 = (
                Person.objects.filter(mobiles__isnull=False)
                .exclude(mobiles__mobile__in=exclude_mobiles)
                .exclude(national_code__in=candidates)
                .distinct()
                .values_list('national_code', flat=True)[: (to_create * 8)]
            )
            candidates = list(set(candidates) | set(fb2))
        if not candidates:
            continue
        random.shuffle(candidates)
        selected_ids = candidates[:to_create]
        persons = Person.objects.filter(national_code__in=selected_ids).prefetch_related('mobiles')
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


def _get_accessible_projects(user: User, panel: str | None = None) -> List[Project]:
    """Return a list of projects accessible to the user.

    If ``panel`` is provided, only projects where the user has that panel
    permission are returned.  Organisation users see all projects for
    which they have a membership (typically all that they created).
    """
    qs = Project.objects.filter(memberships__user=user)
    # If a specific panel permission is requested, filter projects by memberships where that flag is True.
    if panel:
        filter_kwargs = {f"memberships__{panel}": True}
        qs = qs.filter(**filter_kwargs)
    # For organisations, return distinct projects; for individuals, the same applies but they will have only their memberships
    return list(qs.distinct())


@login_required
def project_list(request: HttpRequest) -> HttpResponse:
    """List projects accessible to the logged in organisation user."""
    user = request.user
    if not _user_is_organisation(user):
        messages.warning(request, 'Access denied: only organisation accounts can manage projects.')
        return redirect('home')
    projects = _get_accessible_projects(user)
    return render(request, 'projects_list.html', {'projects': projects})


@login_required
def project_add(request: HttpRequest) -> HttpResponse:
    """Create a new project and assign the creator membership to it."""
    user = request.user
    if not _user_is_organisation(user):
        messages.warning(request, 'Access denied: only organisation accounts can create projects.')
        return redirect('home')
    if request.method == 'POST':
        form = ProjectForm(request.POST)
        if form.is_valid():
            project = form.save(commit=False)
            project.filled_samples = 0
            project.save()
            # assign membership to creator with all panels enabled (for convenience)
            mem = Membership.objects.create(
                user=user,
                project=project,
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
            # log activity
            log_activity(user, 'Created project', f"Project {project.pk}: {project.name}")
            return redirect('project_list')
    else:
        form = ProjectForm()
    return render(request, 'project_form.html', {'form': form, 'title': 'Add Project'})


@login_required
def project_edit(request: HttpRequest, project_id: int) -> HttpResponse:
    """Edit an existing project accessible to the organisation user."""
    user = request.user
    if not _user_is_organisation(user):
        messages.warning(request, 'Access denied: only organisation accounts can edit projects.')
        return redirect('home')
    project = get_object_or_404(Project, pk=project_id)
    # ensure the user has a membership to this project
    if not Membership.objects.filter(project=project, user=user).exists():
        messages.error(request, 'You do not have permission to edit this project.')
        return redirect('project_list')
    if request.method == 'POST':
        form = ProjectForm(request.POST, instance=project)
        if form.is_valid():
            form.save()
            messages.success(request, 'Project updated successfully.')
            # log activity
            log_activity(user, 'Updated project', f"Project {project.pk}: {project.name}")
            return redirect('project_list')
    else:
        form = ProjectForm(instance=project)
    return render(request, 'project_form.html', {'form': form, 'title': 'Edit Project'})


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
    # list all memberships for projects of this organisation
    memberships = Membership.objects.filter(project__memberships__user=user).distinct()
    # map field names to human readable labels for display
    panel_labels = {
        'database_management': 'Database Management',
        'quota_management': 'Quota Management',
        'collection_management': 'Collection Management',
        'collection_performance': 'Collection Performance',
        'telephone_interviewer': 'Telephone Interviewer',
        'fieldwork_interviewer': 'Fieldwork Interviewer',
        'focus_group_panel': 'Focus Group Panel',
        'qc_management': 'QC Management',
        'qc_performance': 'QC Performance',
        'voice_review': 'Voice Review',
        'callback_qc': 'Callback QC',
        'coding': 'Coding',
        'statistical_health_check': 'Statistical Health Check',
        'tabulation': 'Tabulation',
        'statistics': 'Statistics',
        'funnel_analysis': 'Funnel Analysis',
        'conjoint_analysis': 'Conjoint Analysis',
        'segmentation_analysis': 'Segmentation Analysis',
    }
    return render(request, 'membership_list.html', {'memberships': memberships, 'panel_labels': panel_labels})


@login_required
def membership_add(request: HttpRequest) -> HttpResponse:
    """Assign a user to a project with panel permissions (organisation only)."""
    user = request.user
    if not _user_is_organisation(user):
        messages.warning(request, 'Access denied: only organisation accounts can manage memberships.')
        return redirect('home')
    # projects the organisation can assign users to
    accessible_projects = _get_accessible_projects(user)
    if request.method == 'POST':
        form = UserToProjectForm(request.POST)
        form.fields['project'].queryset = Project.objects.filter(pk__in=[p.pk for p in accessible_projects])
        if form.is_valid():
            email = form.cleaned_data['email']
            project = form.cleaned_data['project']
            # find or create user by email
            try:
                target_user = User.objects.get(username=email)
            except User.DoesNotExist:
                messages.error(request, 'No user with that email exists.')
                return render(request, 'membership_form.html', {'form': form, 'title': 'Add User'})
            # ensure membership does not already exist
            if Membership.objects.filter(user=target_user, project=project).exists():
                messages.error(request, 'This user is already assigned to the project.')
                return redirect('membership_list')
            # create membership with selected panels and title
            mem_kwargs = {}
            for field in form.fields:
                if field not in ('email', 'project'):
                    mem_kwargs[field] = form.cleaned_data[field]
            membership = Membership.objects.create(user=target_user, project=project, **mem_kwargs)
            messages.success(request, 'User assigned to project.')
            # log activity
            log_activity(user, 'Added membership', f"User {target_user.username} to Project {project.pk}")
            return redirect('membership_list')
    else:
        form = UserToProjectForm()
        form.fields['project'].queryset = Project.objects.filter(pk__in=[p.pk for p in accessible_projects])
    return render(request, 'membership_form.html', {'form': form, 'title': 'Add User'})


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
    panel_fields = [f for f in UserToProjectForm().fields if f not in ('email', 'project')]
    if request.method == 'POST':
        form = UserToProjectForm(request.POST)
        form.fields['project'].queryset = Project.objects.filter(pk=membership.project.pk)
        # set initial project field to membership.project
        if form.is_valid():
            for field in panel_fields:
                setattr(membership, field, form.cleaned_data[field])
            membership.save()
            messages.success(request, 'Membership updated successfully.')
            # log activity
            log_activity(user, 'Updated membership', f"Membership {membership_id}")
            return redirect('membership_list')
    else:
        initial = {'email': membership.user.email, 'project': membership.project, 'title': membership.title}
        for field in panel_fields:
            initial[field] = getattr(membership, field)
        form = UserToProjectForm(initial=initial)
        form.fields['project'].queryset = Project.objects.filter(pk=membership.project.pk)
        form.fields['email'].widget = forms.HiddenInput()  # type: ignore
        form.fields['project'].widget = forms.HiddenInput()  # type: ignore
    return render(request, 'membership_form.html', {'form': form, 'title': 'Edit User'})


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
    membership_user = membership.user.username
    project_id = membership.project.pk
    membership.delete()
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
    user = request.user
    if not _user_has_panel(user, 'quota_management'):
        messages.error(request, 'Access denied: you do not have quota management permissions.')
        return redirect('home')
    projects = _get_accessible_projects(user, 'quota_management')

    # Determine selected project from query param or session
    project_param = request.GET.get('project') or request.session.get('quota_project')
    selected_project: Project | None = None
    if project_param:
        try:
            selected_project = Project.objects.get(pk=project_param)
            request.session['quota_project'] = selected_project.pk
        except Project.DoesNotExist:
            selected_project = None

    if request.method == 'POST':
        project_id = request.POST.get('project')
        city_data_json = request.POST.get('city_data')
        age_data_json = request.POST.get('age_data')
        if not project_id or not city_data_json or not age_data_json:
            messages.error(request, 'Invalid form submission.')
            return redirect('quota_management')
        try:
            project = Project.objects.get(pk=project_id)
            request.session['quota_project'] = project.pk
        except Project.DoesNotExist:
            messages.error(request, 'Project not found.')
            return redirect('quota_management')
        # ensure user has membership or organisation rights
        if not _user_is_organisation(user) and not Membership.objects.filter(project=project, user=user, quota_management=True).exists():
            messages.error(request, 'You do not have quota permissions for this project.')
            return redirect('quota_management')
        try:
            city_data: List[Dict[str, Any]] = json.loads(city_data_json)
            age_data: List[Dict[str, Any]] = json.loads(age_data_json)
        except json.JSONDecodeError:
            messages.error(request, 'Invalid quota data.')
            return redirect('quota_management')
        # ensure percentages sum to 100 with tolerance
        total_city = sum(float(item.get('quota', 0)) for item in city_data)
        total_age = sum(float(item.get('quota', 0)) for item in age_data)
        if abs(total_city - 100.0) > 0.01 or abs(total_age - 100.0) > 0.01:
            messages.error(request, 'City and age quotas must each sum to 100%.')
            return redirect('quota_management')
        # delete old quotas and build new ones
        Quota.objects.filter(project=project).delete()
        sample_size = int(project.sample_size)
        quota_cells: List[Tuple[str, int, int, int]] = []
        for c in city_data:
            city = str(c['city'])
            city_pct = float(c['quota']) / 100.0
            for a in age_data:
                age_start = int(a['start'])
                age_end = int(a['end'])
                age_pct = float(a['quota']) / 100.0
                target_count = int(round(sample_size * city_pct * age_pct))
                quota_cells.append((city, age_start, age_end, target_count))
        # adjust rounding difference to match sample_size
        diff = sample_size - sum(cell[3] for cell in quota_cells)
        if quota_cells and diff != 0:
            city, age_start, age_end, count = quota_cells[0]
            quota_cells[0] = (city, age_start, age_end, max(count + diff, 0))
        for city, age_start, age_end, count in quota_cells:
            Quota.objects.create(
                project=project,
                city=city,
                age_start=age_start,
                age_end=age_end,
                target_count=count,
                assigned_count=0,
            )
        log_activity(user, 'Saved quotas', f"Project {project.pk}")
        try:
            generate_call_samples(project, replenish=False)
        except Exception:
            pass
        messages.success(request, 'Quotas saved successfully.')
        return redirect(f"{reverse('quota_management')}?project={project.pk}")

    # Build context for GET requests
    # union of all cities present in database and selected project's quotas
    db_cities = set(Person.objects.values_list('city_name', flat=True))
    if selected_project:
        quota_cities = set(Quota.objects.filter(project=selected_project).values_list('city', flat=True))
    else:
        quota_cities = set()
    cities = sorted(db_cities | quota_cities)
    context: Dict[str, Any] = {
        'projects': projects,
        'cities': cities,
        'selected_project': selected_project,
    }
    if selected_project:
        quotas = list(Quota.objects.filter(project=selected_project))
        if quotas:
            city_headers = sorted({q.city for q in quotas})
            age_ranges = sorted({(q.age_start, q.age_end) for q in quotas}, key=lambda x: x[0])
            table_rows: List[Dict[str, Any]] = []
            for (start, end) in age_ranges:
                row_counts: List[Dict[str, Any]] = []
                for city in city_headers:
                    q_match = next((q for q in quotas if q.city == city and q.age_start == start and q.age_end == end), None)
                    if q_match:
                        row_counts.append({
                            'target': q_match.target_count,
                            'assigned': q_match.assigned_count,
                            'over': q_match.assigned_count > q_match.target_count,
                        })
                    else:
                        row_counts.append({'target': 0, 'assigned': 0, 'over': False})
                table_rows.append({'age_label': f"{start}-{end}", 'counts': row_counts})
            # Prefill data for city and age percentages
            total = max(int(selected_project.sample_size), 1)
            city_pct_map: Dict[str, float] = {}
            for c in city_headers:
                s = sum(q.target_count for q in quotas if q.city == c)
                city_pct_map[c] = round((s * 100.0) / total, 2)
            age_prefill: List[Dict[str, Any]] = []
            for (start, end) in age_ranges:
                s = sum(q.target_count for q in quotas if q.age_start == start and q.age_end == end)
                age_prefill.append({
                    'start': start,
                    'end': end,
                    'quota': round((s * 100.0) / total, 2),
                })
            context.update({
                'city_headers': city_headers,
                'table_rows': table_rows,
                'prefill_json': json.dumps({'cities': city_pct_map, 'ages': age_prefill}, ensure_ascii=False),
            })
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
    user = request.user
    if not _user_has_panel(user, 'telephone_interviewer'):
        messages.error(request, 'Access denied: you do not have telephone interviewer permissions.')
        return redirect('home')
    # determine accessible projects for telephone interviewer
    projects = _get_accessible_projects(user, 'telephone_interviewer')
    # selected project id from GET or session
    selected_project_id = request.GET.get('project') or request.session.get('telephone_project')
    selected_project = None
    person_to_call = None
    person_mobile = None
    quota_cell = None
    call_sample_obj = None
    if selected_project_id:
        try:
            selected_project = Project.objects.get(pk=selected_project_id)
        except Project.DoesNotExist:
            selected_project = None
        else:
            # store selection in session for convenience
            request.session['telephone_project'] = selected_project_id
            # handle POST submissions: record interview and mark sample as completed
            if request.method == 'POST':
                call_sample_id = request.POST.get('call_sample_id')
                code_str = request.POST.get('code')
                code = int(code_str) if code_str else None
                status = True if code == 1 else False
                # parse optional fields
                gender_val = request.POST.get('gender')
                gender = None
                if gender_val:
                    gender = True if gender_val == 'male' else False
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
                call_sample = None
                if call_sample_id:
                    try:
                        call_sample = CallSample.objects.get(pk=call_sample_id)
                    except CallSample.DoesNotExist:
                        call_sample = None
                person = call_sample.person if call_sample else None
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
                log_activity(user, 'Recorded interview', f"Project {selected_project.pk}, code {code}, call_sample_id {call_sample_id or ''}")
                # update quota assigned count and mark sample completed
                if call_sample:
                    quota_obj = call_sample.quota
                    quota_obj.assigned_count = quota_obj.assigned_count + 1
                    quota_obj.save()
                    call_sample.completed = True
                    call_sample.completed_at = timezone.now()
                    call_sample.save()
                # update project's filled_samples as number of completed interviews
                selected_project.filled_samples = Interview.objects.filter(project=selected_project, status=True).count()
                selected_project.save()
                messages.success(request, 'Interview recorded.')
                # redirect back to same project to fetch next sample
                return redirect(f"{reverse('telephone_interviewer')}?project={selected_project.pk}")
            # GET: assign or fetch a call sample for the user
            # First, see if the user already has a pending sample
            call_sample = CallSample.objects.filter(
                project=selected_project, assigned_to=user, completed=False
            ).first()
            if not call_sample:
                # Assign the next unassigned sample
                call_sample = CallSample.objects.filter(
                    project=selected_project, assigned_to__isnull=True, completed=False
                ).first()
                if call_sample:
                    call_sample.assigned_to = user
                    call_sample.assigned_at = timezone.now()
                    call_sample.save()
            if not call_sample:
                # No free samples: try to replenish (top up) existing quotas
                try:
                    generate_call_samples(selected_project, replenish=True)
                except Exception:
                    pass
                call_sample = CallSample.objects.filter(
                    project=selected_project, assigned_to__isnull=True, completed=False
                ).first()
                if call_sample:
                    call_sample.assigned_to = user
                    call_sample.assigned_at = timezone.now()
                    call_sample.save()
            if not call_sample:
                # Still no samples: regenerate entire pool from scratch
                try:
                    generate_call_samples(selected_project, replenish=False)
                except Exception:
                    pass
                call_sample = CallSample.objects.filter(
                    project=selected_project, assigned_to__isnull=True, completed=False
                ).first()
                if call_sample:
                    call_sample.assigned_to = user
                    call_sample.assigned_at = timezone.now()
                    call_sample.save()
            if call_sample:
                call_sample_obj = call_sample
                person_to_call = call_sample.person
                person_mobile = call_sample.mobile.mobile if call_sample.mobile else None
                quota_cell = call_sample.quota
    # status codes mapping for display in template
    status_codes = {
        1: 'مصاحبه موفق' if request.session.get('lang', 'en') == 'fa' else 'Successful Interview',
        2: 'پیغام گیر (صندوق صوتی)' if request.session.get('lang', 'en') == 'fa' else 'Voicemail',
        3: 'بعدا تماس بگیرید (با تعیین زمان)' if request.session.get('lang', 'en') == 'fa' else 'Call later (with time)',
        4: 'بعدا تماس بگیرید (بدون تعیین زمان)' if request.session.get('lang', 'en') == 'fa' else 'Call later',
        5: 'اشغال است' if request.session.get('lang', 'en') == 'fa' else 'Busy',
        6: 'جواب نمی‌دهد' if request.session.get('lang', 'en') == 'fa' else 'No answer',
        7: 'مصاحبه ناقص (باید تکمیل شود)' if request.session.get('lang', 'en') == 'fa' else 'Incomplete interview (to be completed)',
        8: 'مصاحبه ناقص (تمایلی به ادامه ندارد)' if request.session.get('lang', 'en') == 'fa' else 'Incomplete (respondent unwilling)',
        9: 'شماره در شبکه موجود نیست' if request.session.get('lang', 'en') == 'fa' else 'Number not in network',
        10: 'مشکل زبان' if request.session.get('lang', 'en') == 'fa' else 'Language barrier',
        11: 'پاسخگو در مدت فیلد در دسترس نیست' if request.session.get('lang', 'en') == 'fa' else 'Respondent unavailable during fieldwork',
        12: 'خاموش است' if request.session.get('lang', 'en') == 'fa' else 'Powered off',
        13: 'عدم همکاری' if request.session.get('lang', 'en') == 'fa' else 'Non‑cooperative',
        14: 'دیگر تماس نگیرید (پاسخگوی عصبانی)' if request.session.get('lang', 'en') == 'fa' else 'Do not call again (angry)',
        15: 'پاسخگوی غیر واجد شرایط' if request.session.get('lang', 'en') == 'fa' else 'Not eligible',
        16: 'بیش از سهمیه' if request.session.get('lang', 'en') == 'fa' else 'Quota exceeded',
        17: 'در دسترس نیست' if request.session.get('lang', 'en') == 'fa' else 'Unavailable',
        18: 'برقراری تماس مقدور نیست' if request.session.get('lang', 'en') == 'fa' else 'Cannot connect',
        19: 'خارج از سرویس' if request.session.get('lang', 'en') == 'fa' else 'Out of service',
        20: 'سایر' if request.session.get('lang', 'en') == 'fa' else 'Other',
        21: 'مصاحبه سوخته' if request.session.get('lang', 'en') == 'fa' else 'Burned interview',
    }
    # Determine start time for the interview form: if a call sample is
    # presented, record the current server time in ISO format so that the
    # template can include it as a hidden field.  This timestamp will be
    # saved to the Interview.start_form field when the form is submitted.
    start_iso = None
    if call_sample_obj:
        start_iso = timezone.now().isoformat()
    context = {
        'projects': projects,
        'selected_project': selected_project,
        'person': person_to_call,
        'mobile': person_mobile,
        'quota_cell': quota_cell,
        'call_sample': call_sample_obj,
        'status_codes': status_codes,
        'start_form': start_iso,
    }
    return render(request, 'telephone_interviewer.html', context)


@login_required
def collection_performance(request: HttpRequest) -> HttpResponse:
    """Collection performance dashboard.

    Renders a page containing a Chart.js bar chart that displays, for
    each user, the total number of interviews they have conducted and
    the number of successful interviews (code == 1).  The chart data is
    provided by an AJAX endpoint and updated every five seconds.
    """
    user = request.user
    if not _user_has_panel(user, 'collection_performance'):
        messages.error(request, 'Access denied: you do not have collection performance permissions.')
        return redirect('home')
    # fetch accessible users (those who share projects with current user)
    # For simplicity we allow an organisation to view all their users.
    # Non‑organisation users only see themselves.
    if _user_is_organisation(user):
        users = User.objects.filter(memberships__project__memberships__user=user).distinct()
    else:
        users = User.objects.filter(pk=user.pk)
    context = {
        'users': users,
    }
    return render(request, 'collection_performance.html', context)


@login_required
def collection_performance_data(request: HttpRequest) -> JsonResponse:
    """Return interview counts per user for the collection performance chart.

    Accepts optional query parameters ``start_date``, ``end_date`` (ISO
    format) and ``users`` (comma separated user IDs) to filter the
    results.  Returns a JSON response with arrays of user names,
    total interview counts and success counts.
    """
    user = request.user
    if not _user_has_panel(user, 'collection_performance'):
        return JsonResponse({'error': 'forbidden'}, status=403)
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    user_ids = request.GET.get('users')
    qs = Interview.objects.all()
    # filter by time range
    if start_date_str:
        try:
            start_dt = datetime.fromisoformat(start_date_str)
            qs = qs.filter(created_at__gte=start_dt)
        except ValueError:
            pass
    if end_date_str:
        try:
            end_dt = datetime.fromisoformat(end_date_str)
            qs = qs.filter(created_at__lte=end_dt)
        except ValueError:
            pass
    # filter by users accessible
    if not _user_is_organisation(user):
        qs = qs.filter(user=user)
    elif user_ids:
        try:
            ids = [int(i) for i in user_ids.split(',') if i.strip()]
            qs = qs.filter(user__id__in=ids)
        except ValueError:
            pass
    # aggregate counts
    agg = qs.values('user__first_name').annotate(
        total=Count('id'),
        success=Count('id', filter=Q(code=1))
    )
    labels: List[str] = []
    totals: List[int] = []
    successes: List[int] = []
    for row in agg:
        labels.append(row['user__first_name'] or str(row['user__first_name']))
        totals.append(row['total'])
        successes.append(row['success'])
    return JsonResponse({'labels': labels, 'totals': totals, 'successes': successes})


@login_required
def collection_performance_export(request: HttpRequest) -> HttpResponse:
    """Export collection performance data to an Excel workbook with charts.

    This view generates an Excel file summarising the number of interviews
    conducted by each user and the number of successful interviews (code
    equal to 1).  It uses ``openpyxl`` to create a workbook with both
    data and a bar chart.  If the ``openpyxl`` library is unavailable,
    a 501 response is returned.

    The optional query parameters ``start_date``, ``end_date`` and
    ``users`` mirror those accepted by the JSON data endpoint.  Only
    users with the ``collection_performance`` panel permission may
    access this endpoint.
    """
    user = request.user
    if not _user_has_panel(user, 'collection_performance'):
        messages.error(request, 'Access denied: you do not have collection performance permissions.')
        return redirect('home')
    if openpyxl is None:
        return JsonResponse({'error': 'Excel export is not available on this server.'}, status=501)
    # replicate filtering logic from collection_performance_data
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    user_ids = request.GET.get('users')
    qs = Interview.objects.all()
    if start_date_str:
        try:
            start_dt = datetime.fromisoformat(start_date_str)
            qs = qs.filter(created_at__gte=start_dt)
        except ValueError:
            pass
    if end_date_str:
        try:
            end_dt = datetime.fromisoformat(end_date_str)
            qs = qs.filter(created_at__lte=end_dt)
        except ValueError:
            pass
    if not _user_is_organisation(user):
        qs = qs.filter(user=user)
    elif user_ids:
        try:
            ids = [int(i) for i in user_ids.split(',') if i.strip()]
            qs = qs.filter(user__id__in=ids)
        except ValueError:
            pass
    agg = qs.values('user__first_name').annotate(
        total=Count('id'),
        success=Count('id', filter=Q(code=1))
    )
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Performance Data'
    ws.append(['User', 'Total Interviews', 'Successful Interviews'])
    for row in agg:
        ws.append([
            row['user__first_name'] or '',
            row['total'],
            row['success'],
        ])
    # build bar chart
    chart = BarChart()
    chart.title = 'Interview Performance'
    chart.x_axis.title = 'User'
    chart.y_axis.title = 'Count'
    data_ref = Reference(ws, min_col=2, min_row=1, max_col=3, max_row=ws.max_row)
    cat_ref = Reference(ws, min_col=1, min_row=2, max_row=ws.max_row)
    chart.add_data(data_ref, titles_from_data=True)
    chart.set_categories(cat_ref)
    chart.width = 20
    chart.height = 10
    ws.add_chart(chart, 'E2')
    # write to buffer
    from io import BytesIO
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    response = HttpResponse(
        buffer.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename=collection_performance.xlsx'
    return response

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
    if not _user_has_panel(user, 'database_management'):
        messages.error(request, 'Access denied: you do not have database management permissions.')
        return redirect('home')
    # Determine which projects the user can manage
    projects = _get_accessible_projects(user, panel='database_management')
    entries = DatabaseEntry.objects.filter(project__in=projects).select_related('project')
    return render(request, 'database_list.html', {'entries': entries})


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
    if not _user_has_panel(user, 'database_management'):
        messages.error(request, 'Access denied: you do not have permission to add databases.')
        return redirect('home')
    projects = _get_accessible_projects(user, panel='database_management')
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
    return render(request, 'database_form.html', {'form': form, 'title': 'Add Database'})


@login_required
def database_edit(request: HttpRequest, pk: int) -> HttpResponse:
    """Edit an existing database entry.

    Only users with the ``database_management`` permission for the
    associated project may edit the entry.  On POST the entry is
    updated.  The status field is not editable here; it will be
    updated by background sync logic.
    """
    user = request.user
    if not _user_has_panel(user, 'database_management'):
        messages.error(request, 'Access denied: you do not have permission to edit databases.')
        return redirect('home')
    entry = get_object_or_404(DatabaseEntry, pk=pk)
    projects = _get_accessible_projects(user, panel='database_management')
    if entry.project not in projects:
        messages.error(request, 'You do not have permission to edit this database.')
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
    return render(request, 'database_form.html', {'form': form, 'title': 'Edit Database'})


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
    snapshot = load_entry_snapshot(entry)
    all_records = snapshot.records
    # NOTE: For very large payloads we may need to stream or cache slices client-side
    # to avoid loading the full JSON into memory during rendering.
    total_records = len(all_records)
    page_sizes = [30, 50, 200]
    default_page_size = page_sizes[1]
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
    if not (_user_has_panel(user, 'qc_management') or _user_has_panel(user, 'qc_performance')):
        messages.error(request, 'Access denied: you do not have quality control permissions.')
        return redirect('home')

    project_qs = Project.objects.filter(memberships__user=user)
    if not _user_is_organisation(user):
        project_qs = project_qs.filter(Q(memberships__qc_management=True) | Q(memberships__qc_performance=True))
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
    page_sizes = [30, 50, 200]
    default_page_size = 50
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
    if not (_user_is_organisation(user) or Membership.objects.filter(
        user=user,
        project=project,
    ).filter(Q(qc_management=True) | Q(qc_performance=True)).exists()):
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
