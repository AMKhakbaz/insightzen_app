"""Utilities for working with Persian (Jalali) dates.

This module centralises helper functions that convert Gregorian
timestamps to the Jalali calendar and derive age calculations based on
Persian dates.  Several parts of the application (e.g. telephone
interviewer and quota dashboards) need consistent logic for translating
stored birth years/dates into user facing ages within the Jalali
calendar.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Optional

import jdatetime
from django.utils import timezone

__all__ = [
    'calculate_age_from_birth_info',
]

# Regular expression used to extract numeric fragments from a stored
# birth date string.  Birth dates can arrive in multiple formats
# (YYYY/MM/DD, YYYY-MM-DD, etc.), so we fall back to parsing the numeric
# components in order.
_DATE_FRAGMENT_RE = re.compile(r"\d+")


def _jalali_from_components(year: int, month: int = 1, day: int = 1) -> Optional[jdatetime.date]:
    """Build a Jalali date from the provided components.

    Years greater than 1700 are assumed to be Gregorian and converted to
    Jalali using :func:`jdatetime.date.fromgregorian`.  Jalali years are
    expected to be in the 13xx/14xx range.  Invalid dates (e.g. out of
    range month/day) return ``None`` rather than raising.
    """

    if year <= 0:
        return None

    try:
        if year > 1700:
            return jdatetime.date.fromgregorian(date=date(year, month, day))
        return jdatetime.date(year, month, day)
    except ValueError:
        return None


def _parse_birth_string(value: str) -> Optional[jdatetime.date]:
    """Attempt to convert a stored birth date string to a Jalali date."""

    fragments = _DATE_FRAGMENT_RE.findall(value)
    if not fragments:
        return None

    # Prefer YYYY/MM/DD style strings.  If only a year is provided we
    # fall back to the 1st of Farvardin for calculations.
    if len(fragments) >= 3:
        year, month, day = (int(fragments[0]), int(fragments[1]), int(fragments[2]))
        jalali_date = _jalali_from_components(year, month, day)
        if jalali_date is not None:
            return jalali_date

    # If we only have a year component, treat it as such.
    try:
        year_only = int(fragments[0])
    except (TypeError, ValueError):
        return None
    return _jalali_from_components(year_only)


def _resolve_birth_jalali(birth_year: Optional[int], birth_date: Optional[str]) -> Optional[jdatetime.date]:
    """Determine the Jalali birth date from stored year/date fields."""

    if birth_date:
        parsed = _parse_birth_string(birth_date)
        if parsed is not None:
            return parsed

    if birth_year is None:
        return None

    return _jalali_from_components(int(birth_year))


def calculate_age_from_birth_info(birth_year: Optional[int], birth_date: Optional[str]) -> Optional[int]:
    """Compute the respondent's age using Jalali calendar arithmetic.

    The function converts the stored birth information to a Jalali date
    (defaulting to Farvardin 1st when only the year is known) and
    subtracts it from the current Jalali date.  A non-negative integer
    age is returned, or ``None`` when insufficient data is available.
    """

    birth_jalali = _resolve_birth_jalali(birth_year, birth_date)
    if birth_jalali is None:
        return None

    today_gregorian = timezone.localdate()
    today_jalali = jdatetime.date.fromgregorian(date=today_gregorian)

    age = today_jalali.year - birth_jalali.year
    # Adjust when the birthday has not yet occurred in the current year.
    if (today_jalali.month, today_jalali.day) < (birth_jalali.month, birth_jalali.day):
        age -= 1

    return age if age >= 0 else None
