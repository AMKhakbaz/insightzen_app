"""Utility helpers for pulling the respondent bank from the main database.

These helpers encapsulate the connection details and copy logic for syncing
the respondent bank (``Person``/``Mobile`` rows) from the primary PostgreSQL
instance.  They are used by management commands such as
``import_respondent_bank`` to keep application startup free of database work
or interactive prompts.
"""

from __future__ import annotations

from typing import Dict, Iterable

from django.core.exceptions import ImproperlyConfigured

import psycopg2
from psycopg2 import sql

from insightzen.db_env import respondent_postgres_config

from .models import Mobile, Person
from .services.gender_utils import normalize_gender_value


def _stream_table(conn, table_name: str) -> Iterable[Dict[str, object]]:
    """Yield dictionaries representing each row of the given table."""

    cursor_name = f"{table_name}_cursor"
    with conn.cursor(name=cursor_name) as cur:
        cur.itersize = 5000
        cur.execute(sql.SQL('SELECT * FROM {}').format(sql.Identifier(table_name)))

        first_row = cur.fetchone()
        if first_row is None:
            return

        if cur.description is None:
            raise RuntimeError(
                f'Cursor description is unavailable for table "{table_name}"; '
                'cannot stream rows without column metadata.'
            )

        colnames = [desc[0] for desc in cur.description]

        yield {colnames[i]: first_row[i] for i in range(len(colnames))}

        for row in cur:
            yield {colnames[i]: row[i] for i in range(len(colnames))}


def load_people_and_mobile() -> None:
    """Copy all person and mobile rows from the primary PostgreSQL DB."""

    try:
        db_config = respondent_postgres_config()
    except RuntimeError as exc:
        raise ImproperlyConfigured(str(exc)) from exc

    conn = psycopg2.connect(
        host=db_config['HOST'],
        port=int(db_config['PORT']),
        database=db_config['NAME'],
        user=db_config['USER'],
        password=db_config['PASSWORD'],
    )
    try:
        _copy_people(conn)
        _copy_mobiles(conn)
    finally:
        conn.close()


def _copy_people(conn) -> None:
    buffer: list[Person] = []
    for row in _stream_table(conn, 'core_person'):
        nat_code = str(row.get('national_code') or '').strip()
        if not nat_code:
            continue
        birth_year = row.get('birth_year')
        city_name = row.get('city_name')
        if birth_year in (None, '') or city_name in (None, ''):
            continue
        buffer.append(
            Person(
                national_code=nat_code,
                full_name=row.get('full_name'),
                birth_year=int(birth_year),
                city_name=str(city_name),
                gender=normalize_gender_value(row.get('gender')),
            )
        )
        if len(buffer) >= 5000:
            Person.objects.bulk_create(buffer, ignore_conflicts=True)
            buffer.clear()
    if buffer:
        Person.objects.bulk_create(buffer, ignore_conflicts=True)


def _copy_mobiles(conn) -> None:
    buffer: list[Mobile] = []
    for row in _stream_table(conn, 'core_mobile'):
        mobile_value = row.get('mobile') or row.get('phone') or row.get('mobile_number')
        person_id = row.get('person_id') or row.get('national_code')
        if not mobile_value or not person_id:
            continue
        buffer.append(
            Mobile(
                mobile=str(mobile_value),
                person_id=str(person_id),
            )
        )
        if len(buffer) >= 5000:
            Mobile.objects.bulk_create(buffer, ignore_conflicts=True)
            buffer.clear()
    if buffer:
        Mobile.objects.bulk_create(buffer, ignore_conflicts=True)