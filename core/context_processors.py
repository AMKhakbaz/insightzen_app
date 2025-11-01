"""Custom context processors for the core application.

Context processors add extra variables into the context of every template
rendered by Django. Here we expose the currently selected language (stored
in the user's session) so that templates can adjust their presentation
accordingly.
"""

from __future__ import annotations

from typing import Any, Dict


def language(request) -> Dict[str, Any]:
    """Expose common variables (language and panel access) to all templates.

    In addition to the language preference, templates often need to know
    which panels are enabled for the current user.  This function
    inspects the user's memberships and determines, for each panel, if
    they should be displayed.  Organisation users automatically have
    access to all panels.  The result is a dictionary containing the
    language code and a ``panels_enabled`` dictionary mapping panel
    keys to booleans.
    """
    lang = request.session.get('lang', 'en')
    panels_enabled = {}
    # Default all panels to False
    panel_fields = [
        'database_management', 'quota_management', 'collection_management',
        'collection_performance', 'telephone_interviewer', 'fieldwork_interviewer',
        'focus_group_panel', 'qc_management', 'qc_performance', 'voice_review',
        'callback_qc', 'coding', 'statistical_health_check', 'tabulation',
        'statistics', 'funnel_analysis', 'conjoint_analysis', 'segmentation_analysis'
    ]
    for pf in panel_fields:
        panels_enabled[pf] = False
    user = getattr(request, 'user', None)
    if user and user.is_authenticated:
        profile = getattr(user, 'profile', None)
        # Organisation users have access to everything
        if profile and profile.organization:
            for pf in panel_fields:
                panels_enabled[pf] = True
        else:
            # Aggregate panel permissions across all memberships
            for membership in getattr(user, 'memberships', []).all():
                for pf in panel_fields:
                    panels_enabled[pf] = panels_enabled[pf] or getattr(membership, pf)
    return {
        'lang': lang,
        'panels_enabled': panels_enabled,
    }