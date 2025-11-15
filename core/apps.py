"""Application configuration for the core app.

This module defines a custom ``AppConfig`` for the ``core`` app.  On
application startup, it checks whether the ``Person`` table is empty and
prompts the operator to optionally load data from an external PostgreSQL
database.  This allows an administrator to prepopulate the ``people`` and
``mobile`` tables via the console when launching the development server
for the first time.
"""

from __future__ import annotations

import sys
from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Custom AppConfig to perform initial data loading on startup."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self) -> None:
        """Ask the user whether to load initial people/mobile data.

        When the application starts via the ``runserver`` command and no
        people records exist, this method prompts the user on the
        console.  If confirmed, it copies the entire respondent bank from
        the reference PostgreSQL database into the local store so the app
        can run with real data immediately.
        """
        # Only run this prompt when using the development server
        if 'runserver' not in sys.argv:
            return
        # Delay imports until runtime to avoid circular imports and handle
        # cases where the database may not be fully initialised yet.
        from django.db import OperationalError
        try:
            from .models import Person
            # If the table does not exist yet, this call will raise
            # OperationalError (e.g., during migrations).  In that case we
            # skip prompting entirely.
            if Person.objects.exists():
                return
        except OperationalError:
            # Database not ready; do nothing
            return
        try:
            # Prompt the operator
            resp = input(
                'Respondent bank is empty. Download data from the main database now? [y/N] '
            ).strip().lower()
        except Exception:
            # If input is not possible (e.g., in non‑interactive environments)
            return
        if resp not in {'y', 'yes'}:
            print('Skipping respondent bank import; continuing setup without remote data.')
            return
        # Import utility lazily
        from . import data_load_utils

        try:
            data_load_utils.load_people_and_mobile()
            print('Respondent bank imported successfully.')
        except Exception as exc:
            print(f'Failed to load data: {exc}')