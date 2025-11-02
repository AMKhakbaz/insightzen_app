"""
Synchronise external database entries into the InsightZen PostgreSQL database.

This management command iterates over ``DatabaseEntry`` records and
invokes the generic KoboToolbox ETL routine to import new submissions
into PostgreSQL tables.  It uses the credentials stored on each
``DatabaseEntry`` to construct a ``FormSpec`` and executes a single
synchronisation run via ``surveyzen_etl_generic.run_once``.

Environment variables PG_HOST, PG_PORT, PG_DBNAME, PG_USER and
PG_PASSWORD are temporarily set based on the Django database
configuration to ensure the ETL writes into the InsightZen database.
After each entry is processed its ``status``, ``last_sync`` and
``last_error`` fields are updated accordingly.

Usage:
    python manage.py sync_database_entries

You may schedule this command via cron or Celery beat to run at your
desired interval (e.g. every 10 minutes) to keep external data tables
up to date.  If you wish to synchronise only a specific entry, pass
the ``--entry`` option with the entry's primary key.
"""

from __future__ import annotations

import os
from typing import Optional

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.conf import settings

from core.models import DatabaseEntry

try:
    # Import the ETL helper module which exposes run_once and FormSpec
    from surveyzen_etl_generic import run_once, FormSpec, sanitize_identifier
except Exception as e:  # pragma: no cover
    raise ImportError(f"Failed to import ETL module: {e}")


class Command(BaseCommand):
    help = "Synchronise external database entries into the InsightZen database."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            '--entry',
            type=int,
            help='Synchronise only the specified DatabaseEntry primary key',
        )
        parser.add_argument(
            '--loop',
            action='store_true',
            help='Continuously loop every 10 minutes to synchronise entries',
        )

    def handle(self, *args, **options) -> None:
        entry_id: Optional[int] = options.get('entry')
        loop: bool = options.get('loop', False)

        def run_sync() -> None:
            if entry_id:
                entries = DatabaseEntry.objects.filter(pk=entry_id)
                if not entries:
                    raise CommandError(f"No DatabaseEntry found with id {entry_id}")
            else:
                entries = DatabaseEntry.objects.all()

            # Read DB config from Django settings and set PG_* environment variables
            db_conf = settings.DATABASES.get('default', {})
            os.environ['PG_HOST'] = db_conf.get('HOST', '') or '127.0.0.1'
            os.environ['PG_PORT'] = str(db_conf.get('PORT', 5432))
            os.environ['PG_DBNAME'] = db_conf.get('NAME', '')
            os.environ['PG_USER'] = db_conf.get('USER', '')
            os.environ['PG_PASSWORD'] = db_conf.get('PASSWORD', '') or db_conf.get('PGPASSWORD', '') or ''

            for entry in entries:
                self.stdout.write(f"Synchronising entry {entry.pk}: {entry.db_name} (project {entry.project_id})...")
                # Build table name from asset_id (sanitise)
                table_name = sanitize_identifier(entry.asset_id)
                form = FormSpec(api_token=entry.token, asset_uid=entry.asset_id, main_table=table_name)
                try:
                    inserted_main, inserted_rep = run_once(form)
                    entry.status = True
                    entry.last_error = ''
                    self.stdout.write(f"Inserted main={inserted_main}, repeats={inserted_rep} for entry {entry.pk}")
                except Exception as e:  # pragma: no cover
                    entry.status = False
                    entry.last_error = str(e)
                    self.stderr.write(f"Error synchronising entry {entry.pk}: {e}")
                entry.last_sync = timezone.now()
                entry.save()
            self.stdout.write(self.style.SUCCESS('Database synchronisation complete.'))

        if loop:
            import time
            while True:
                run_sync()
                # Sleep for 10 minutes
                time.sleep(600)
        else:
            run_sync()