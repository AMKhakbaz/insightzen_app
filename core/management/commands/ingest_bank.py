"""Management command to ingest large Bank SQL dumps.

This command loads a two-table backup (persons and mobiles) into a
temporary ``staging`` schema and then merges the data into the
application tables.  It is designed to handle tens of millions of
records efficiently using PostgreSQL COPY.  The command expects a
``Bank.sql`` file created via pgAdmin's Plain backup (with COPY
statements) to be placed next to ``manage.py``.  See the README for
instructions on producing this file.

Usage::

    python manage.py ingest_bank --file Bank.sql

The command accepts optional flags to prepare the staging schema
only, to skip the merge step, and to specify the path to the psql
executable.  When merging, duplicate records are ignored via
``ON CONFLICT`` clauses.  Indexes and ANALYZE should be run after
ingestion using the ``tune_db`` command.
"""

import os
import subprocess
import shlex
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


# SQL statements to prepare staging schema and tables
SQL_PREP = """
CREATE SCHEMA IF NOT EXISTS staging;
CREATE UNLOGGED TABLE IF NOT EXISTS staging.person (
    national_code varchar(10) PRIMARY KEY,
    full_name varchar(145),
    father_name varchar(35),
    birth_year bigint,
    birth_date varchar(10),
    city_name varchar(22),
    province_name varchar(20),
    birth_city varchar(22),
    birth_province varchar(20)
);
CREATE UNLOGGED TABLE IF NOT EXISTS staging.mobile (
    mobile varchar(15) PRIMARY KEY,
    person_id varchar(10) NOT NULL
);
"""

# SQL statements to merge staging into core tables
SQL_MERGE = """
SET LOCAL synchronous_commit = off;

INSERT INTO core_person (national_code, full_name, father_name, birth_year, birth_date,
                        city_name, province_name, birth_city, birth_province, imputation)
SELECT p.national_code, p.full_name, p.father_name, p.birth_year, p.birth_date,
       p.city_name, p.province_name, p.birth_city, p.birth_province, false
FROM staging.person p
ON CONFLICT (national_code) DO NOTHING;

INSERT INTO core_mobile (mobile, person_id)
SELECT m.mobile, m.person_id
FROM staging.mobile m
JOIN core_person cp ON cp.national_code = m.person_id
ON CONFLICT (mobile) DO NOTHING;
"""


class Command(BaseCommand):
    help = "Load Bank.sql into staging and merge into core tables."

    def add_arguments(self, parser):
        parser.add_argument('--file', default='Bank.sql', help='Path to Bank.sql (or Bank.sql.gz)')
        parser.add_argument('--psql', default=os.environ.get('PSQL_BIN', 'psql'), help='Path to psql binary')
        parser.add_argument('--schema-only', action='store_true', help='Only create staging schema, skip loading and merge')
        parser.add_argument('--skip-merge', action='store_true', help='Load staging but skip merging into core tables')

    def handle(self, *args, **options):
        bank_file = options['file']
        psql_bin = options['psql']
        if not os.path.exists(bank_file):
            raise CommandError(f"Bank file not found: {bank_file}")
        self.stdout.write(self.style.NOTICE('Preparing staging schema...'))
        with connection.cursor() as cur:
            cur.execute(SQL_PREP)
        if options['schema-only']:
            self.stdout.write(self.style.SUCCESS('Staging schema created.'))
            return
        # Build psql command to run Bank.sql (handles .gz via shell pipeline)
        dsn = self._build_dsn()
        if bank_file.endswith('.gz'):
            cmd = f"gzip -dc {shlex.quote(bank_file)} | {psql_bin} {dsn} -v ON_ERROR_STOP=1 -f -"
        else:
            cmd = f"{psql_bin} {dsn} -v ON_ERROR_STOP=1 -f {shlex.quote(bank_file)}"
        self.stdout.write(self.style.NOTICE('Loading Bank.sql into PostgreSQL...'))
        self._run(cmd)
        self.stdout.write(self.style.SUCCESS('Bank.sql executed successfully.'))
        if options['skip-merge']:
            self.stdout.write(self.style.WARNING('Skipping merge step as requested.'))
            return
        # Merge staging tables into core tables
        self.stdout.write(self.style.NOTICE('Merging staging data into core tables...'))
        with connection.cursor() as cur:
            cur.execute('BEGIN;')
            cur.execute('SET LOCAL work_mem = %s;', [os.environ.get('PG_WORK_MEM', '512MB')])
            cur.execute(SQL_MERGE)
            cur.execute('COMMIT;')
        self.stdout.write(self.style.SUCCESS('Merge completed.'))

    def _build_dsn(self) -> str:
        """Build a DSN string for psql using Django settings."""
        from django.conf import settings
        db = settings.DATABASES['default']
        host = db.get('HOST', '127.0.0.1')
        port = db.get('PORT', '5432')
        name = db.get('NAME', 'insightzen')
        user = db.get('USER', 'postgres')
        return f"-h {shlex.quote(str(host))} -p {shlex.quote(str(port))} -U {shlex.quote(str(user))} -d {shlex.quote(str(name))}"

    def _run(self, cmd: str):
        """Run a shell command and stream output to the console."""
        proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in proc.stdout:
            self.stdout.write(line.rstrip())
        ret = proc.wait()
        if ret != 0:
            raise CommandError(f"Command failed with exit code {ret}: {cmd}")