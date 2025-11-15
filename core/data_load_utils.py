"""Utility functions for loading data from external sources.

This module contains helper functions used to import large datasets
into the InsightZen application's SQLite database.  The ``load_people_and_mobile``
function connects to a remote PostgreSQL database and retrieves rows
from the ``people`` and ``mobile`` tables.  The retrieved data is
converted into the local ``Person`` and ``Mobile`` Django models and
saved using bulk inserts for efficiency.
"""

from __future__ import annotations

import psycopg2
from typing import Iterable, Tuple

from .models import Person, Mobile
from .services.gender_utils import normalize_gender_value


# Connection parameters for the remote PostgreSQL database.  These values
# should remain in sync with the user's configuration.  It may be
# desirable to read these from environment variables or a settings file
# rather than hard coding them here.
DB_HOST = "192.168.10.83"
DB_NAME = "Numbers"
DB_USER = "postgres"
DB_PASSWORD = "cri#49146"


def _fetch_rows(cur, query: str) -> Iterable[Tuple]:
    """Execute a query and yield rows lazily.

    This helper function executes the provided SQL query using the
    given cursor.  Fetching results in batches keeps memory usage
    manageable when dealing with very large tables.
    """
    cur.execute(query)
    while True:
        rows = cur.fetchmany(10000)
        if not rows:
            break
        for row in rows:
            yield row


def load_people_and_mobile(all_data: bool = False) -> None:
    """Load people and mobile data from the remote database into SQLite.

    Args:
        all_data: If True, download all rows from the remote tables.  If
            False, download a sample of approximately 100,000 people and
            the corresponding mobile numbers.

    This implementation introspects the column names of the remote
    tables to accommodate variations in schema (e.g., ``address`` vs
    ``addres``).  It selects either all rows or a limited subset and
    maps them into the local ``Person`` and ``Mobile`` models.  Bulk
    inserts are used for efficiency and existing records are ignored.
    """
    conn = psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASSWORD)
    try:
        with conn.cursor() as cur:
            # Fetch all or sample of people
            people_base_query = "SELECT * FROM people"
            if not all_data:
                people_base_query += " LIMIT 100000"
            cur.execute(people_base_query)
            # Determine column names from cursor description
            colnames = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
            people_to_create: list[Person] = []
            sampled_codes: list[str] = []
            for row in rows:
                row_dict = {colnames[i]: row[i] for i in range(len(colnames))}
                nat_code = str(row_dict.get('national_code') or row_dict.get('National_code') or row_dict.get('nationalCode'))
                if not nat_code:
                    continue
                sampled_codes.append(nat_code)
                birth_year_value = row_dict.get('birth_year') or row_dict.get('birthYear')
                city_value = row_dict.get('city_name') or row_dict.get('city')
                if birth_year_value in (None, '') or city_value in (None, ''):
                    continue
                person = Person(
                    national_code=nat_code,
                    full_name=row_dict.get('full_name') or row_dict.get('fullname') or row_dict.get('fullName'),
                    birth_year=int(birth_year_value),
                    city_name=str(city_value),
                    gender=normalize_gender_value(row_dict.get('gender')),
                )
                people_to_create.append(person)
            # Bulk insert people (ignore conflicts on duplicate national_code)
            Person.objects.bulk_create(people_to_create, ignore_conflicts=True)
            # Determine mobile rows to fetch
            with conn.cursor() as cur2:
                if all_data:
                    mobile_query = "SELECT * FROM mobile"
                else:
                    if not sampled_codes:
                        mobile_query = None
                    else:
                        # Use tuple to prevent SQL injection
                        codes_tuple = tuple(sampled_codes)
                        placeholder = ','.join(['%s'] * len(codes_tuple))
                        mobile_query = f"SELECT * FROM mobile WHERE national_code IN ({placeholder})"
                mobiles_to_create: list[Mobile] = []
                if mobile_query:
                    if all_data:
                        cur2.execute(mobile_query)
                        mobile_colnames = [desc[0] for desc in cur2.description]
                        for row in cur2.fetchall():
                            row_dict = {mobile_colnames[i]: row[i] for i in range(len(mobile_colnames))}
                            mobile_num = str(row_dict.get('mobile') or row_dict.get('phone') or row_dict.get('mobile_number'))
                            nat_code = row_dict.get('national_code') or row_dict.get('nationalCode')
                            if mobile_num and nat_code:
                                mobiles_to_create.append(Mobile(mobile=mobile_num, person_id=str(nat_code)))
                    else:
                        cur2.execute(mobile_query, codes_tuple)
                        mobile_colnames = [desc[0] for desc in cur2.description]
                        for row in cur2.fetchall():
                            row_dict = {mobile_colnames[i]: row[i] for i in range(len(mobile_colnames))}
                            mobile_num = str(row_dict.get('mobile') or row_dict.get('phone') or row_dict.get('mobile_number'))
                            nat_code = row_dict.get('national_code') or row_dict.get('nationalCode')
                            if mobile_num and nat_code:
                                mobiles_to_create.append(Mobile(mobile=mobile_num, person_id=str(nat_code)))
                    # Bulk insert mobiles
                    Mobile.objects.bulk_create(mobiles_to_create, ignore_conflicts=True)
    finally:
        conn.close()