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
        console.  The user may choose to download all data or a sample
        subset.  Data is retrieved from a remote PostgreSQL database
        specified in the project documentation and saved into the local
        SQLite database.
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
            resp = input('No people data found. Download data from remote database? [y/N] ').strip().lower()
        except Exception:
            # If input is not possible (e.g., in non‑interactive environments)
            return
        if resp != 'y':
            return
        try:
            sample_choice = input('Download all data or a 100k sample? [all/100k] ').strip().lower()
        except Exception:
            return
        # Import utility lazily
        from . import data_load_utils
        all_data = sample_choice == 'all'
        try:
            data_load_utils.load_people_and_mobile(all_data)
            print('Data loaded successfully.')
        except Exception as exc:
            print(f'Failed to load data: {exc}')