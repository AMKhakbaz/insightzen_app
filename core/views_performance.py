"""Views for the enhanced collection performance dashboard.

This module provides an improved implementation of the collection
performance dashboard and its supporting APIs.  In addition to the
stacked bar chart previously available, the new dashboard offers a
donut chart illustrating interview contributions per interviewer for
the selected project, a daily trend line chart and a sortable table
highlighting the top interviewers.  An extended Excel export is also
provided, including a raw data sheet listing every call.

The views defined here mirror the names of the previous endpoints so
that existing URLs continue to work.  If you wish to customise the
behaviour further, adjust the aggregation logic or chart data as
needed.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Sequence

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from .models import Interview, Project
# Reuse helper functions from the main views module.  In addition to
# _user_has_panel and _user_is_organisation we also import
# _get_accessible_projects so we can filter interview data to only
# projects the current user is permitted to view.
from .views import (
    _user_has_panel,
    _user_is_organisation,
    _get_accessible_projects,
    _get_locked_projects,
)


def _parse_datetime_param(value: str | None) -> datetime | None:
    """Return a timezone-aware datetime parsed from an ISO string."""

    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _normalise_multi_value(raw_values: Sequence[str]) -> List[str]:
    """Expand comma-separated values in list-style query parameters."""

    expanded: List[str] = []
    for value in raw_values:
        if not value:
            continue
        if ',' in value:
            expanded.extend([part.strip() for part in value.split(',') if part.strip()])
        else:
            expanded.append(value.strip())
    return expanded


def _extract_filters(
    request: HttpRequest,
    accessible_projects: List[Project],
) -> Dict[str, object]:
    """Parse query parameters shared by the dashboard and export views."""

    accessible_ids = {proj.id for proj in accessible_projects}

    raw_project_params = request.GET.getlist('projects')
    if not raw_project_params and request.GET.get('project'):
        raw_project_params = [request.GET['project']]
    project_ids: List[int] = []
    invalid_projects: List[int] = []
    for value in _normalise_multi_value(raw_project_params):
        try:
            project_id = int(value)
        except (TypeError, ValueError):
            continue
        if project_id in accessible_ids and project_id not in project_ids:
            project_ids.append(project_id)
        else:
            invalid_projects.append(project_id)
    if invalid_projects:
        raise PermissionError('project_locked')

    raw_user_params = request.GET.getlist('users')
    if not raw_user_params and request.GET.get('users'):
        raw_user_params = [request.GET['users']]
    user_ids: List[int] = []
    for value in _normalise_multi_value(raw_user_params):
        try:
            user_id = int(value)
        except (TypeError, ValueError):
            continue
        if user_id not in user_ids:
            user_ids.append(user_id)

    start_raw = request.GET.get('start_date')
    end_raw = request.GET.get('end_date')

    return {
        'project_ids': project_ids,
        'user_ids': user_ids,
        'start_dt': _parse_datetime_param(start_raw),
        'end_dt': _parse_datetime_param(end_raw),
        'start_raw': start_raw or '',
        'end_raw': end_raw or '',
    }


def _filter_interviews(
    user: User,
    accessible_projects: List[Project],
    filters: Dict[str, object],
):
    """Return an Interview queryset filtered by the supplied parameters."""

    project_ids: List[int] = filters.get('project_ids', [])  # type: ignore[assignment]
    user_ids: List[int] = filters.get('user_ids', [])  # type: ignore[assignment]
    start_dt: datetime | None = filters.get('start_dt')  # type: ignore[assignment]
    end_dt: datetime | None = filters.get('end_dt')  # type: ignore[assignment]

    qs = Interview.objects.select_related('project', 'user').filter(project__in=accessible_projects)
    if project_ids:
        qs = qs.filter(project__id__in=project_ids)
    if start_dt:
        qs = qs.filter(created_at__gte=start_dt)
    if end_dt:
        qs = qs.filter(created_at__lte=end_dt)
    if not _user_is_organisation(user):
        qs = qs.filter(user=user)
    elif user_ids:
        qs = qs.filter(user__id__in=user_ids)
    return qs


def _build_chart_payload(qs) -> Dict[str, object]:
    """Aggregate interview data into chart/table structures."""

    bar_labels: List[str] = []
    bar_totals: List[int] = []
    bar_successes: List[int] = []
    bar_projects: List[Dict[str, object]] = []
    for row in (
        qs.values('project__id', 'project__name')
        .annotate(total=Count('id'), success=Count('id', filter=Q(code=1)))
        .order_by('project__name')
    ):
        label = row['project__name'] or ''
        bar_labels.append(label)
        bar_totals.append(row['total'])
        bar_successes.append(row['success'])
        bar_projects.append({
            'id': row['project__id'],
            'name': label,
            'total': row['total'],
            'success': row['success'],
        })

    donut_labels: List[str] = []
    donut_values: List[int] = []
    donut_segments: List[Dict[str, object]] = []
    for row in (
        qs.values('project__name', 'user__id', 'user__first_name')
        .annotate(total=Count('id'))
        .order_by('-total', 'project__name', 'user__first_name')
    ):
        user_label = row['user__first_name'] or str(row['user__id'])
        project_label = row['project__name'] or ''
        combined_label = f"{project_label} — {user_label}" if project_label else user_label
        donut_labels.append(combined_label)
        donut_values.append(row['total'])
        donut_segments.append({
            'project': project_label,
            'user': user_label,
            'label': combined_label,
            'value': row['total'],
        })

    daily_labels: List[str] = []
    daily_totals: List[int] = []
    daily_successes: List[int] = []
    for row in (
        qs.annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(total=Count('id'), success=Count('id', filter=Q(code=1)))
        .order_by('day')
    ):
        day = row['day']
        day_str = day.isoformat() if hasattr(day, 'isoformat') else str(day)
        daily_labels.append(day_str)
        daily_totals.append(row['total'])
        daily_successes.append(row['success'])

    top_rows: List[Dict[str, object]] = []
    for row in (
        qs.values('project__id', 'project__name', 'user__id', 'user__first_name')
        .annotate(total=Count('id'), success=Count('id', filter=Q(code=1)))
        .order_by('-total', 'project__name', 'user__first_name')
    ):
        total = row['total']
        success = row['success']
        rate = (success / total * 100) if total else 0
        top_rows.append({
            'project_id': row['project__id'],
            'project': row['project__name'] or '',
            'user_id': row['user__id'],
            'user': row['user__first_name'] or str(row['user__id']),
            'total': total,
            'success': success,
            'rate': round(rate, 2),
        })

    return {
        'bar': {
            'labels': bar_labels,
            'totals': bar_totals,
            'successes': bar_successes,
            'projects': bar_projects,
        },
        'donut': {
            'labels': donut_labels,
            'values': donut_values,
            'segments': donut_segments,
        },
        'daily': {
            'labels': daily_labels,
            'totals': daily_totals,
            'successes': daily_successes,
        },
        'top': {
            'rows': top_rows,
        },
        'meta': {
            'total_interviews': sum(bar_totals),
            'successful_interviews': sum(bar_successes),
        },
    }

# Attempt to import openpyxl for Excel export
try:
    import openpyxl  # type: ignore
    from openpyxl.chart import BarChart, Reference
except Exception:
    openpyxl = None  # type: ignore


@login_required
def collection_performance(request: HttpRequest) -> HttpResponse:
    """Render the enhanced collection performance dashboard.

    This view prepares the list of projects and users accessible to the
    current user and renders the dashboard template.  Only users with
    the ``collection_performance`` panel permission may access this
    page.  Organisation accounts see all projects they participate in,
    whereas individual interviewers only see their own projects.
    """
    user = request.user
    if not _user_has_panel(user, 'collection_performance'):
        messages.error(request, 'Access denied: you do not have collection performance permissions.')
        return redirect('home')
    # Determine accessible projects: organisations see all their
    # membership projects; individuals see only their own.
    # Build the list of projects for which the user has the collection_performance panel permission.
    accessible_projects = _get_accessible_projects(user, panel='collection_performance')
    if not accessible_projects:
        locked = _get_locked_projects(user, panel='collection_performance')
        if locked:
            locked_names = ', '.join(sorted({p.name for p in locked}))
            messages.error(
                request,
                f'Access denied: project deadlines have passed ({locked_names}). Only the owner can continue to view the collection performance dashboard.',
            )
        else:
            messages.error(request, 'Access denied: there are no projects available for collection performance analytics.')
        return redirect('home')
    try:
        filters = _extract_filters(request, accessible_projects)
    except PermissionError:
        messages.error(request, 'Requested project is not available for this dashboard.')
        return redirect('collection_performance')

    if _user_is_organisation(user):
        users_qs = User.objects.filter(memberships__project__in=accessible_projects).distinct()
        selected_user_ids = filters['user_ids']  # type: ignore[index]
    else:
        users_qs = User.objects.filter(pk=user.pk)
        selected_user_ids = [user.pk]

    context = {
        'projects': sorted(accessible_projects, key=lambda p: p.name.lower()),
        'users': users_qs.order_by('first_name'),
        'filters': {
            'project_ids': filters['project_ids'],  # type: ignore[index]
            'user_ids': selected_user_ids,
            'start': filters['start_raw'],  # type: ignore[index]
            'end': filters['end_raw'],  # type: ignore[index]
        },
    }
    return render(request, 'collection_performance.html', context)


@login_required
def collection_performance_data(request: HttpRequest) -> JsonResponse:
    """Return aggregated interview statistics for performance charts."""

    user = request.user
    if not _user_has_panel(user, 'collection_performance'):
        return JsonResponse({'error': 'forbidden'}, status=403)

    accessible_projects = _get_accessible_projects(user, panel='collection_performance')
    if not accessible_projects:
        return JsonResponse(
            {
                'bar': {'labels': [], 'totals': [], 'successes': [], 'projects': []},
                'donut': {'labels': [], 'values': [], 'segments': []},
                'daily': {'labels': [], 'totals': [], 'successes': []},
                'top': {'rows': []},
                'meta': {'total_interviews': 0, 'successful_interviews': 0},
            }
        )

    try:
        filters = _extract_filters(request, accessible_projects)
    except PermissionError:
        return JsonResponse({'error': 'project_locked'}, status=403)

    qs = _filter_interviews(user, accessible_projects, filters)
    payload = _build_chart_payload(qs)
    payload['filters'] = {
        'projects': filters['project_ids'],  # type: ignore[index]
        'users': filters['user_ids'],  # type: ignore[index]
        'start_date': filters['start_raw'],  # type: ignore[index]
        'end_date': filters['end_raw'],  # type: ignore[index]
    }
    return JsonResponse(payload)

@login_required
def collection_performance_export(request: HttpRequest) -> HttpResponse:
    """Export the filtered collection performance dataset to Excel."""

    user = request.user
    if not _user_has_panel(user, 'collection_performance'):
        messages.error(request, 'Access denied: you do not have collection performance permissions.')
        return redirect('home')
    if openpyxl is None:
        return JsonResponse({'error': 'Excel export is not available on this server.'}, status=501)

    accessible_projects = _get_accessible_projects(user, panel='collection_performance')
    if not accessible_projects:
        messages.error(request, 'Access denied: there are no projects available for collection performance analytics.')
        return redirect('collection_performance')

    try:
        filters = _extract_filters(request, accessible_projects)
    except PermissionError:
        messages.error(request, 'Requested project is not available for export.')
        return redirect('collection_performance')

    qs = _filter_interviews(user, accessible_projects, filters)
    payload = _build_chart_payload(qs)
    qs_rows = qs.select_related('project', 'user', 'person').prefetch_related('person__mobiles').order_by('created_at')

    wb = openpyxl.Workbook()
    ws_summary = wb.active
    ws_summary.title = 'Summary'
    ws_summary.append(['Project', 'Total Interviews', 'Successful Interviews'])
    for project in payload['bar']['projects']:
        ws_summary.append([project['name'], project['total'], project['success']])

    if ws_summary.max_row > 1:
        chart = BarChart()
        chart.title = 'Interview Performance'
        chart.x_axis.title = 'Project'
        chart.y_axis.title = 'Count'
        data_ref = Reference(ws_summary, min_col=2, min_row=1, max_col=3, max_row=ws_summary.max_row)
        cat_ref = Reference(ws_summary, min_col=1, min_row=2, max_row=ws_summary.max_row)
        chart.add_data(data_ref, titles_from_data=True)
        chart.set_categories(cat_ref)
        chart.width = 20
        chart.height = 10
        ws_summary.add_chart(chart, 'E2')

    ws_top = wb.create_sheet(title='TopInterviewers')
    ws_top.append(['Project', 'User', 'Total Interviews', 'Successful Interviews', 'Success Rate (%)'])
    for row in payload['top']['rows']:
        ws_top.append([row['project'], row['user'], row['total'], row['success'], row['rate']])

    ws_raw = wb.create_sheet(title='RawCalls')
    ws_raw.append([
        'DateTime', 'Project', 'Interviewer', 'Phone', 'Code', 'Status',
        'City', 'Age', 'BirthYear', 'Gender', 'StartForm', 'EndForm'
    ])
    for iv in qs_rows:
        phone = ''
        if iv.person and hasattr(iv.person, 'mobiles'):
            mobile = iv.person.mobiles.first()
            if mobile:
                phone = mobile.mobile
        status_str = 'Success' if (iv.code == 1 or iv.status) else 'Other'
        start_form_str = iv.start_form.isoformat(sep=' ') if iv.start_form else ''
        end_form_str = iv.end_form.isoformat(sep=' ') if iv.end_form else ''
        ws_raw.append([
            iv.created_at.isoformat(sep=' '),
            iv.project.name,
            iv.user.first_name or '',
            phone,
            iv.code,
            status_str,
            iv.city or '',
            iv.age if iv.age is not None else '',
            iv.birth_year if iv.birth_year is not None else '',
            ('M' if iv.gender is False else 'F') if iv.gender is not None else '',
            start_form_str,
            end_form_str,
        ])

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

