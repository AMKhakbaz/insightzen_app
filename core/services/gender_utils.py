"""Helpers for normalising and mapping gender values across the app."""

from __future__ import annotations

from typing import Any, Optional

GENDER_ALIASES = {
    'male': 'male',
    'm': 'male',
    'man': 'male',
    'مرد': 'male',
    'آقا': 'male',
    'اقا': 'male',
    'خانوم': 'female',
    'خانم': 'female',
    'female': 'female',
    'f': 'female',
    'woman': 'female',
    'زن': 'female',
}


def normalize_gender_value(value: Any) -> Optional[str]:
    """Return a canonical gender value (male/female) when recognised."""

    if value in (None, ''):
        return None
    text = str(value).strip().lower()
    return GENDER_ALIASES.get(text)


def gender_value_from_boolean(value: Optional[bool]) -> Optional[str]:
    """Map stored boolean interview gender flags to canonical strings."""

    if value is True:
        return 'male'
    if value is False:
        return 'female'
    return None


def boolean_from_gender_value(value: Any) -> Optional[bool]:
    """Convert canonical string values back into boolean flags."""

    normalized = normalize_gender_value(value)
    if normalized == 'male':
        return True
    if normalized == 'female':
        return False
    return None
