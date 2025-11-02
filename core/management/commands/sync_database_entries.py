"""Refresh the JSON cache for external database entries.

This management command iterates over ``DatabaseEntry`` records and
downloads their Kobo submissions into the JSON cache maintained by
``core.services.database_cache``.  After each refresh the ``status``,
``last_sync`` and ``last_error`` fields are updated so the management
UI reflects the outcome of the synchronisation.

Usage::

    python manage.py sync_database_entries

You may schedule this command via cron or a task runner to execute
periodically.  The ``--entry`` option limits the run to a single
``DatabaseEntry`` primary key, while ``--loop`` keeps the command
running, sleeping ten minutes between iterations.
"""

from __future__ import annotations

from typing import Optional

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.models import DatabaseEntry
from core.services.database_cache import DatabaseCacheError, refresh_entry_cache


class Command(BaseCommand):
    help = "Refresh cached Kobo payloads for DatabaseEntry records."

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

            for entry in entries:
                self.stdout.write(
                    f"Refreshing cache for entry {entry.pk}: {entry.db_name} (project {entry.project_id})..."
                )
                try:
                    result = refresh_entry_cache(entry)
                    entry.status = True
                    entry.last_error = ''
                    self.stdout.write(
                        f"Cached {result.total} submissions (added {result.added}, updated {result.updated})."
                    )
                except DatabaseCacheError as exc:
                    entry.status = False
                    entry.last_error = str(exc)
                    self.stderr.write(f"Error synchronising entry {entry.pk}: {exc}")
                entry.last_sync = timezone.now()
                entry.save(update_fields=['status', 'last_error', 'last_sync'])
            self.stdout.write(self.style.SUCCESS('Database cache refresh complete.'))

        if loop:
            import time
            while True:
                run_sync()
                # Sleep for 10 minutes
                time.sleep(600)
        else:
            run_sync()