"""Management command to tune database indexes and statistics.

This command creates important indexes on the main data tables used by
the application and optionally drops the staging schema used for
ingesting Bank.sql.  Creating indexes concurrently minimises
interruption of write operations on large tables.  Afterwards, the
command runs ANALYSE to update planner statistics.

Usage::

    python manage.py tune_db --concurrently

The ``--concurrently`` flag tells PostgreSQL to build the indexes
without exclusive locks.  Without it, the command will take a
shorter time but requires a lock that might block writes.

You can also specify ``--drop-staging`` to remove the temporary
``staging`` schema after the merge is complete.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Create indexes and analyse database after importing bank data."

    def add_arguments(self, parser):
        parser.add_argument(
            '--concurrently',
            action='store_true',
            help='Build indexes concurrently to avoid locking writes',
        )
        parser.add_argument(
            '--drop-staging',
            action='store_true',
            help='Drop the staging schema after tuning (use after merging data)',
        )

    def handle(self, *args, **options):
        concurrently = options['concurrently']
        drop_staging = options['drop_staging']
        self.stdout.write(self.style.NOTICE('Starting database tuning...'))
        # Prepare index creation statements.  Include concurrently keyword if requested.
        idx_kw = 'CONCURRENTLY' if concurrently else ''
        index_statements = [
            f'CREATE INDEX {idx_kw} IF NOT EXISTS core_person_city_birth_idx ON core_person (city_name, birth_year);',
            f'CREATE INDEX {idx_kw} IF NOT EXISTS core_person_birth_idx ON core_person (birth_year);',
            f'CREATE INDEX {idx_kw} IF NOT EXISTS core_mobile_person_id_idx ON core_mobile (person_id);',
        ]
        analyze_statement = 'ANALYZE;'  # run planner statistics update
        drop_schema_stmt = 'DROP SCHEMA IF EXISTS staging CASCADE;' if drop_staging else None
        with connection.cursor() as cur:
            for stmt in index_statements:
                self.stdout.write(self.style.NOTICE(f'Executing: {stmt}'))
                cur.execute(stmt)
            # Run analyse for improved query planning
            self.stdout.write(self.style.NOTICE('Running ANALYZE on all tables...'))
            cur.execute(analyze_statement)
            # Optionally drop staging schema
            if drop_schema_stmt:
                self.stdout.write(self.style.NOTICE('Dropping staging schema...'))
                cur.execute(drop_schema_stmt)
        self.stdout.write(self.style.SUCCESS('Database tuning completed successfully.'))