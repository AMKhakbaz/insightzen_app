"""Custom template filters for the core app."""

from __future__ import annotations

import re
from typing import Any, Dict, List

from django import template
from django.templatetags.static import static
from django.urls import NoReverseMatch, reverse

register = template.Library()

_ICON_NAME_SANITIZER = re.compile(r"[^a-z0-9_-]")

# New filter to access a dictionary value by key in templates
@register.filter
def get(value, key):
    """Return the value of ``value[key]`` for dictionaries in templates.

    Usage::

        {{ mydict|get:var }}

    This helper tries to return ``value[key]`` if ``value`` implements
    ``dict.get``.  It is useful in templates where accessing a
    dictionary by a variable key (e.g., ``row[col]``) is not allowed by
    the Django template engine.  If the key does not exist or an
    exception occurs, an empty string is returned.

    Args:
        value: A dictionary-like object.
        key: The key to retrieve.

    Returns:
        The value for the given key or an empty string if not found.
    """
    try:
        if hasattr(value, 'get'):
            return value.get(key, '')
        return ''
    except Exception:
        return ''


@register.filter
def attr(obj, attr_name: str):
    """Retrieve an attribute from an object dynamically in templates.

    Usage in a Django template:

    .. code-block:: django

        {{ myobject|attr:"field_name" }}

    This filter will attempt to get the attribute named ``field_name`` from
    ``myobject`` and return its value. If the attribute does not exist,
    ``None`` is returned instead of raising an exception.

    Args:
        obj: The object from which to retrieve the attribute.
        attr_name: Name of the attribute to retrieve.

    Returns:
        The value of the requested attribute or ``None`` if it does not
        exist.
    """
    return getattr(obj, attr_name, None)

@register.filter
def startswith(value, arg: str) -> bool:
    """Return True if the given string starts with the specified prefix.

    This filter mirrors Python's ``str.startswith`` method for use in
    templates. It is useful when template logic needs to conditionally
    include content based on the beginning of a string, such as field
    names or identifiers.

    Args:
        value: The string to test.
        arg: The prefix to look for.

    Returns:
        A boolean indicating whether ``value`` begins with ``arg``.
    """
    if value is None:
        return False
    return str(value).startswith(str(arg))

# Custom tag to render active panel labels for a membership
@register.simple_tag
def panel_names(membership, panel_labels) -> str:
    """Return a comma-separated list of panel labels enabled for a membership.

    This helper iterates over ``panel_labels`` (mapping of field name to human
    readable label) and includes those labels where the corresponding
    membership attribute is truthy.  Usage in template:

    .. code-block:: django

        {% load custom_tags %}
        {% panel_names membership panel_labels as names %}
        {{ names }}

    Args:
        membership: A Membership instance.
        panel_labels: Dict mapping membership field names to display labels.

    Returns:
        A string containing enabled panel labels separated by commas.
    """
    try:
        labels = [label for field, label in panel_labels.items() if getattr(membership, field)]
        return ', '.join(labels)
    except Exception:
        return ''


@register.simple_tag
def feather_icon(name: str | None) -> str:
    """Return the static path for a bundled Feather icon."""

    if not name:
        return ''
    normalized = _ICON_NAME_SANITIZER.sub('', str(name).lower())
    if not normalized:
        return ''
    return static(f'core/icons/feather/{normalized}.svg')


def _resolve_url(name: str | None) -> str:
    """Safely resolve a URL name to its absolute path."""

    if not name:
        return '#'
    try:
        return reverse(name)
    except NoReverseMatch:
        return '#'


@register.inclusion_tag('partials/sidebar_menu.html', takes_context=True)
def render_sidebar(context: Dict[str, Any]) -> Dict[str, Any]:
    """Render the sidebar navigation using a consistent menu schema."""

    user = context.get('user')
    panels_enabled: Dict[str, bool] = context.get('panels_enabled', {}) or {}
    lang = context.get('lang', 'en')
    request = context.get('request')
    current_path = getattr(request, 'path', '')

    is_authenticated = bool(getattr(user, 'is_authenticated', False))
    profile = getattr(user, 'profile', None)
    has_org = bool(getattr(profile, 'organization', None)) if is_authenticated else False
    is_superuser = bool(getattr(user, 'is_superuser', False))

    def panel_active(key: str) -> bool:
        return bool(panels_enabled.get(key, False))

    def url_is_active(url: str | None) -> bool:
        if not url or url == '#':
            return False
        if not current_path:
            return False
        if url == '/':
            return current_path == '/'
        normalized_target = url.rstrip('/')
        normalized_current = current_path.rstrip('/')
        return normalized_current.startswith(normalized_target)

    sections: List[Dict[str, Any]] = [
        {
            'key': 'home',
            'collapsible': False,
            'visible': True,
            'items': [
                {
                    'icon': 'home',
                    'label': {'en': 'Home', 'fa': 'خانه'},
                    'url': _resolve_url('home'),
                    'disabled': False,
                    'visible': True,
                },
            ],
        },
    ]

    if is_superuser:
        sections.append(
            {
                'key': 'superadmin',
                'title': {'en': 'Super Admin', 'fa': 'سوپراَد‌مین'},
                'icon': 'shield',
                'collapsible': True,
                'default_open': True,
                'visible': True,
                'items': [
                    {
                        'icon': 'monitor',
                        'label': {'en': 'Dashboard', 'fa': 'داشبورد'},
                        'url': _resolve_url('superadmin_dashboard'),
                        'disabled': False,
                        'visible': True,
                    },
                    {
                        'icon': 'layers',
                        'label': {'en': 'All Projects', 'fa': 'همه پروژه‌ها'},
                        'url': _resolve_url('project_list'),
                        'disabled': False,
                        'visible': True,
                    },
                    {
                        'icon': 'users',
                        'label': {'en': 'Memberships', 'fa': 'اعضا'},
                        'url': _resolve_url('membership_list'),
                        'disabled': False,
                        'visible': True,
                    },
                    {
                        'icon': 'database',
                        'label': {'en': 'Respondent Bank Sync', 'fa': 'همگام‌سازی بانک پاسخگو'},
                        'url': _resolve_url('database_list'),
                        'disabled': False,
                        'visible': True,
                    },
                    {
                        'icon': 'bell',
                        'label': {'en': 'Notifications & Logs', 'fa': 'اعلان‌ها و لاگ‌ها'},
                        'url': _resolve_url('activity_logs'),
                        'disabled': False,
                        'visible': True,
                    },
                ],
            }
        )

    sections.extend([
        {
            'key': 'management',
            'title': {'en': 'Management', 'fa': 'مدیریت'},
            'icon': 'folder',
            'collapsible': True,
            'default_open': True,
            'visible': True,
            'items': [
                {
                    'icon': 'database',
                    'label': {'en': 'Database Management', 'fa': 'مدیریت پایگاه داده'},
                    'url': _resolve_url('database_list'),
                    'disabled': not panel_active('database_management'),
                    'visible': True,
                },
                {
                    'icon': 'briefcase',
                    'label': {'en': 'Project Management', 'fa': 'مدیریت پروژه'},
                    'url': _resolve_url('project_list'),
                    'disabled': not has_org,
                    'visible': True,
                },
                {
                    'icon': 'sliders',
                    'label': {'en': 'Quota Management', 'fa': 'مدیریت سهمیه'},
                    'url': _resolve_url('quota_management'),
                    'disabled': not panel_active('quota_management'),
                    'visible': True,
                },
                {
                    'icon': 'users',
                    'label': {'en': 'User Management', 'fa': 'مدیریت کاربران'},
                    'url': _resolve_url('membership_list'),
                    'disabled': not has_org,
                    'visible': True,
                },
            ],
        },
        {
            'key': 'collection',
            'title': {'en': 'Collection', 'fa': 'گردآوری'},
            'icon': 'package',
            'collapsible': True,
            'default_open': False,
            'visible': True,
            'items': [
                {
                    'icon': 'archive',
                    'label': {'en': 'Collection Management', 'fa': 'مدیریت گردآوری'},
                    'url': '#',
                    'disabled': not panel_active('collection_management'),
                    'visible': True,
                },
                {
                    'icon': 'bar-chart-2',
                    'label': {'en': 'Collection Performance', 'fa': 'کارایی گردآوری'},
                    'url': _resolve_url('collection_performance'),
                    'disabled': not panel_active('collection_performance'),
                    'visible': True,
                },
                {
                    'icon': 'phone-call',
                    'label': {'en': 'Telephone Interviewer', 'fa': 'مصاحبه تلفنی'},
                    'url': _resolve_url('telephone_interviewer'),
                    'disabled': not panel_active('telephone_interviewer'),
                    'visible': True,
                },
                {
                    'icon': 'map-pin',
                    'label': {'en': 'Fieldwork Interviewer', 'fa': 'مصاحبه میدانی'},
                    'url': '#',
                    'disabled': not panel_active('fieldwork_interviewer'),
                    'visible': True,
                },
                {
                    'icon': 'users',
                    'label': {'en': 'Focus Group Panel', 'fa': 'گروه کانونی'},
                    'url': '#',
                    'disabled': not panel_active('focus_group_panel'),
                    'visible': True,
                },
            ],
        },
        {
            'key': 'quality-control',
            'title': {'en': 'Quality Control', 'fa': 'کنترل کیفیت'},
            'icon': 'check-circle',
            'collapsible': True,
            'default_open': False,
            'visible': True,
            'items': [
                {
                    'icon': 'settings',
                    'label': {'en': 'QC Management', 'fa': 'مدیریت QC'},
                    'url': _resolve_url('qc_management'),
                    'disabled': not panel_active('qc_management'),
                    'visible': True,
                },
                {
                    'icon': 'activity',
                    'label': {'en': 'QC Performance', 'fa': 'کارایی QC'},
                    'url': _resolve_url('qc_performance_dashboard'),
                    'disabled': True,
                    'visible': True,
                },
                {
                    'icon': 'eye',
                    'label': {'en': 'Review Data', 'fa': 'بازبینی داده'},
                    'url': _resolve_url('qc_review'),
                    'disabled': not panel_active('review_data'),
                    'visible': True,
                },
                {
                    'icon': 'edit-3',
                    'label': {'en': 'General Edit', 'fa': 'ویرایش عمومی'},
                    'url': _resolve_url('qc_edit'),
                    'disabled': not panel_active('edit_data'),
                    'visible': True,
                },
                {
                    'icon': 'cpu',
                    'label': {'en': 'Coding AI', 'fa': 'کدگذاری هوش مصنوعی'},
                    'url': _resolve_url('coding'),
                    'disabled': not panel_active('coding'),
                    'visible': True,
                },
                {
                    'icon': 'grid',
                    'label': {'en': 'Product Matrix AI', 'fa': 'ماتریس محصول هوش مصنوعی'},
                    'url': _resolve_url('product_matrix_ai'),
                    'disabled': True,
                    'visible': True,
                },
            ],
        },
        {
            'key': 'mranalysis',
            'title': {'en': 'MRAnalysis', 'fa': 'تحلیل تحقیقات بازار'},
            'icon': 'pie-chart',
            'collapsible': True,
            'default_open': False,
            'visible': True,
            'items': [
                {
                    'icon': 'grid',
                    'label': {'en': 'Tabulation', 'fa': 'جدول‌بندی'},
                    'url': '#',
                    'disabled': not panel_active('tabulation'),
                    'visible': True,
                },
                {
                    'icon': 'trending-up',
                    'label': {'en': 'Statistics', 'fa': 'آمار'},
                    'url': '#',
                    'disabled': not panel_active('statistics'),
                    'visible': True,
                },
                {
                    'icon': 'filter',
                    'label': {'en': 'Funnel Analysis', 'fa': 'تحلیل قیف'},
                    'url': '#',
                    'disabled': not panel_active('funnel_analysis'),
                    'visible': True,
                },
                {
                    'icon': 'layers',
                    'label': {'en': 'Conjoint Analysis', 'fa': 'تحلیل همگرایی'},
                    'url': _resolve_url('conjoint'),
                    'disabled': not panel_active('conjoint_analysis'),
                    'visible': True,
                },
                {
                    'icon': 'divide-square',
                    'label': {'en': 'Segmentation Analysis', 'fa': 'تحلیل تقسیم‌بندی'},
                    'url': '#',
                    'disabled': not panel_active('segmentation_analysis'),
                    'visible': True,
                },
            ],
        },
        {
            'key': 'logs',
            'title': {'en': 'Logs', 'fa': 'گزارش‌ها'},
            'icon': 'file-text',
            'collapsible': True,
            'default_open': False,
            'visible': is_superuser,
            'items': [
                {
                    'icon': 'list',
                    'label': {'en': 'Activity Logs', 'fa': 'لاگ فعالیت‌ها'},
                    'url': _resolve_url('activity_logs'),
                    'disabled': not (has_org or is_superuser),
                    'visible': True,
                },
            ],
        },
    ])

    for section in sections:
        items = section.get('items', [])
        has_active = False
        for item in items:
            is_active = url_is_active(item.get('url'))
            item['is_active'] = is_active
            if is_active:
                has_active = True
        section['has_active'] = has_active
        default_open = section.get('default_open', False)
        section['is_open'] = has_active or default_open

    return {
        'sections': sections,
        'lang': lang,
    }
