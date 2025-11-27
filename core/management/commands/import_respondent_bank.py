"""Import the respondent bank from the primary PostgreSQL database.

This management command mirrors the old ``CoreConfig.ready()`` behaviour but
runs on demand instead of during application startup.  It copies all rows from
the configured respondent database into the local ``Person`` and ``Mobile``
tables using the helpers in :mod:`core.data_load_utils`.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import OperationalError


class Command(BaseCommand):
    help = "Copy respondent bank records into the local database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Import even if respondent data already exists.",
        )
        parser.add_argument(
            "--no-input",
            action="store_true",
            help="Run without an interactive confirmation prompt.",
        )

    def handle(self, *args, **options):
        from core.models import Person

        try:
            if Person.objects.exists() and not options["force"]:
                self.stdout.write(
                    self.style.WARNING(
                        "Respondent bank already contains data; use --force to import anyway."
                    )
                )
                return
        except OperationalError as exc:
            raise CommandError(
                "Database is not ready; ensure migrations have been applied before importing."
            ) from exc

        if not options["no_input"]:
            try:
                answer = input(
                    "This will download and insert the respondent bank from the primary "
                    "database. Proceed? [y/N] "
                ).strip()
            except EOFError as exc:
                raise CommandError(
                    "Interactive input is not available; re-run with --no-input to proceed without confirmation."
                ) from exc

            if answer.lower() not in {"y", "yes"}:
                self.stdout.write(self.style.WARNING("Import cancelled."))
                return

        self.stdout.write(self.style.NOTICE("Importing respondent bank..."))
        from core import data_load_utils

        try:
            data_load_utils.load_people_and_mobile()
        except Exception as exc:  # pragma: no cover - passthrough to existing helper
            raise CommandError(f"Failed to import respondent bank: {exc}") from exc

        self.stdout.write(self.style.SUCCESS("Respondent bank imported successfully."))
