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
import json
from typing import Dict, List

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Count, Q, F
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render

from .models import Interview, Project
# Reuse helper functions from the main views module.  In addition to
# _user_has_panel and _user_is_organisation we also import
# _get_accessible_projects so we can filter interview data to only
# projects the current user is permitted to view.
from .views import (
    _user_has_panel,
    _user_is_organisation,
    _get_accessible_projects,
)

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
    # Determine which interviewers to display: organisation users can see members of these projects; individual users see themselves.
    if _user_is_organisation(user):
        users_qs = User.objects.filter(memberships__project__in=accessible_projects).distinct()
    else:
        users_qs = User.objects.filter(pk=user.pk)
    context = {
        'projects': sorted(accessible_projects, key=lambda p: p.name),
        'users': users_qs.order_by('first_name'),
    }
    return render(request, 'collection_performance.html', context)


@login_required
def collection_performance_data(request: HttpRequest) -> JsonResponse:
    """Return aggregated interview statistics for performance charts.

    Accepts optional query parameters:

      - ``start_date``: ISO 8601 datetime string.  Interviews created
        after this time are included.  If omitted, all records are
        considered.
      - ``end_date``: ISO 8601 datetime string.  Interviews created
        before this time are included.
      - ``project``: integer ID of a project.  When provided, the
        donut chart will display contributions per interviewer for this
        project and the bar/line charts will be filtered to the
        selected project.
      - ``users``: comma‑separated list of user IDs.  Only interviews
        conducted by these users are included in the aggregates.  If
        omitted and the current user is an organisation, all users
        across the accessible projects are included.

    The JSON response contains keys for the bar chart (``labels``,
    ``totals``, ``successes``), the donut chart (``donut`` with
    ``labels`` and ``values``), the daily trend line (``daily`` with
    ``labels``, ``totals`` and ``successes``) and a list of top
    interviewers (``top5_all``) sorted descending by total interviews.
    The client is responsible for choosing which subset of the top
    interviewers to display.
    """
    user = request.user
    if not _user_has_panel(user, 'collection_performance'):
        return JsonResponse({'error': 'forbidden'}, status=403)

    # Parse filters from query parameters
    start_date_str: str | None = request.GET.get('start_date')
    end_date_str: str | None = request.GET.get('end_date')
    project_id_str: str | None = request.GET.get('project')
    user_ids_param: str | None = request.GET.get('users')
    # Start with all interviews and filter down based on access permissions.
    qs = Interview.objects.all()
    # Filter by date range
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
    # Filter by project if specified
    if project_id_str:
        try:
            pid = int(project_id_str)
            qs = qs.filter(project__id=pid)
        except ValueError:
            pass
    # Restrict by membership: only include interviews from projects where the user has the collection_performance permission.
    accessible_projects = _get_accessible_projects(user, panel='collection_performance')
    if accessible_projects:
        qs = qs.filter(project__in=accessible_projects)
    else:
        # No accessible projects: return empty result early
        return JsonResponse({
            'labels': [], 'totals': [], 'successes': [],
            'donut': {'labels': [], 'values': []},
            'daily': {'labels': [], 'totals': [], 'successes': []},
            'top5_all': []
        })
    # Restrict to current user if not organisation
    if not _user_is_organisation(user):
        qs = qs.filter(user=user)
    else:
        # Filter by selected user IDs if provided
        if user_ids_param:
            try:
                ids = [int(i) for i in user_ids_param.split(',') if i.strip()]
                qs = qs.filter(user__id__in=ids)
            except ValueError:
                pass
    # Aggregate for bar chart: count per user
    bar_agg = qs.values('user__first_name').annotate(
        total=Count('id'),
        success=Count('id', filter=Q(code=1))
    ).order_by('-total')
    labels: List[str] = []
    totals: List[int] = []
    successes: List[int] = []
    for row in bar_agg:
        labels.append(row['user__first_name'] or str(row['user__first_name']))
        totals.append(row['total'])
        successes.append(row['success'])
    # Donut chart: contributions per interviewer for selected project
    donut: Dict[str, List] = {'labels': [], 'values': []}
    if project_id_str:
        qs_donut = qs  # already filtered by project
        donut_agg = qs_donut.values('user__first_name').annotate(
            total=Count('id')
        ).order_by('-total')
        donut['labels'] = [row['user__first_name'] or str(row['user__first_name']) for row in donut_agg]
        donut['values'] = [row['total'] for row in donut_agg]
    # Daily trend: group by date
    daily: Dict[str, List] = {'labels': [], 'totals': [], 'successes': []}
    daily_agg = qs.annotate(day=F('created_at__date')).values('day').annotate(
        total=Count('id'),
        success=Count('id', filter=Q(code=1))
    ).order_by('day')
    for row in daily_agg:
        day_str = row['day'].isoformat() if hasattr(row['day'], 'isoformat') else str(row['day'])
        daily['labels'].append(day_str)
        daily['totals'].append(row['total'])
        daily['successes'].append(row['success'])
    # Full ranking of interviewers for top5 table
    top_all = []
    for row in bar_agg:
        total_count = row['total']
        success_count = row['success']
        rate = float(success_count) / total_count if total_count else 0.0
        top_all.append({
            'user': row['user__first_name'] or str(row['user__first_name']),
            'total': total_count,
            'success': success_count,
            'rate': round(rate * 100.0, 2),
        })
    # Sort by total descending for top table; client may re‑sort
    top_all_sorted = sorted(top_all, key=lambda x: (-x['total'], x['user']))
    return JsonResponse({
        'labels': labels,
        'totals': totals,
        'successes': successes,
        'donut': donut,
        'daily': daily,
        'top5_all': top_all_sorted,
    })


@login_required
def collection_performance_export(request: HttpRequest) -> HttpResponse:
    """Export collection performance data along with raw call details to Excel.

    Generates an Excel workbook containing two sheets:

      - ``Summary``: aggregated statistics per interviewer, mirroring
        the data returned by the JSON API (total interviews and
        successful interviews).
      - ``RawCalls``: a detailed log of every interview included by
        the selected filters, listing the date/time, project name,
        interviewer, respondent phone number, code and other fields.

    Accepts the same query parameters as ``collection_performance_data``.
    Users without the ``collection_performance`` panel permission are
    redirected to the home page with an error message.  If
    ``openpyxl`` is not available, a 501 response is returned.
    """
    user = request.user
    if not _user_has_panel(user, 'collection_performance'):
        messages.error(request, 'Access denied: you do not have collection performance permissions.')
        return redirect('home')
    if openpyxl is None:
        return JsonResponse({'error': 'Excel export is not available on this server.'}, status=501)
    # Extract filters
    start_date_str: str | None = request.GET.get('start_date')
    end_date_str: str | None = request.GET.get('end_date')
    project_id_str: str | None = request.GET.get('project')
    user_ids_param: str | None = request.GET.get('users')
    qs = Interview.objects.select_related('project', 'user', 'person').all()
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
    if project_id_str:
        try:
            pid = int(project_id_str)
            qs = qs.filter(project__id=pid)
        except ValueError:
            pass
    if not _user_is_organisation(user):
        qs = qs.filter(user=user)
    else:
        if user_ids_param:
            try:
                ids = [int(i) for i in user_ids_param.split(',') if i.strip()]
                qs = qs.filter(user__id__in=ids)
            except ValueError:
                pass
    # Only include interviews from projects where the current user has collection_performance permission.
    accessible_projects = _get_accessible_projects(user, panel='collection_performance')
    qs = qs.filter(project__in=accessible_projects)
    # Aggregate summary
    agg = qs.values('user__first_name').annotate(
        total=Count('id'),
        success=Count('id', filter=Q(code=1))
    ).order_by('user__first_name')
    # Prepare workbook
    wb = openpyxl.Workbook()
    ws_summary = wb.active
    ws_summary.title = 'Summary'
    ws_summary.append(['User', 'Total Interviews', 'Successful Interviews'])
    for row in agg:
        ws_summary.append([
            row['user__first_name'] or '',
            row['total'],
            row['success'],
        ])
    # Build bar chart on Summary sheet
    chart = BarChart()
    chart.title = 'Interview Performance'
    chart.x_axis.title = 'User'
    chart.y_axis.title = 'Count'
    data_ref = Reference(ws_summary, min_col=2, min_row=1, max_col=3, max_row=ws_summary.max_row)
    cat_ref = Reference(ws_summary, min_col=1, min_row=2, max_row=ws_summary.max_row)
    chart.add_data(data_ref, titles_from_data=True)
    chart.set_categories(cat_ref)
    chart.width = 20
    chart.height = 10
    ws_summary.add_chart(chart, 'E2')
    # Raw calls sheet
    ws_raw = wb.create_sheet(title='RawCalls')
    ws_raw.append([
        'DateTime', 'Project', 'Interviewer', 'Phone', 'Code', 'Status',
        'City', 'Age', 'BirthYear', 'Gender', 'StartForm', 'EndForm'
    ])
    for iv in qs.order_by('created_at'):
        # Determine phone number: first mobile of the person if available
        phone = ''
        if iv.person and hasattr(iv.person, 'mobiles'):
            mob = iv.person.mobiles.first()
            if mob:
                phone = mob.mobile
        status_str = 'Success' if (iv.code == 1 or iv.status) else 'Other'
        # Prepare start and end form timestamps as ISO strings, fallback to empty string
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
    # Write to HTTP response
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