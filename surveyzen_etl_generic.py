#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Generic KoboToolbox (KPI v2 JSON) -> PostgreSQL ETL (Single‑Form, Insert‑Only)

This module is adapted from a script supplied by the user.  It provides
helpers to synchronise data from KoboToolbox (or SurveyZen) into the
InsightZen PostgreSQL database using only INSERT operations.  The API
token and asset UID must be supplied at runtime.  Tables are created
dynamically based on the form definition fetched from the KPI API.
Only new records (based on the `_id` field) are inserted on each run.

Key modifications from the original script:

* Database connection parameters (PG_HOST, PG_PORT, PG_DBNAME,
  PG_USER, PG_PASSWORD) are obtained from environment variables
  rather than being hardcoded.  This allows the Django management
  command to pass the application's database credentials through
  the environment prior to calling ``run_once``.
* The module exposes a function ``run_once`` which executes a single
  synchronisation cycle for the given form specification.  This
  function returns a tuple ``(inserted_main, inserted_repeat)``
  indicating how many records were inserted into the main table and
  repeat tables.  Callers should handle exceptions and update
  status fields accordingly.

Note: This module does not implement scheduling.  Use the
``sync_database_entries`` management command (or a cron job) to run
``run_once`` periodically.
"""

from __future__ import annotations

import argparse
import json
import re
import time
import logging
import logging.handlers
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple, Optional, Iterator

import os
import requests
import pandas as pd  # type: ignore
import psycopg2  # type: ignore
from psycopg2 import sql  # type: ignore
from psycopg2.extras import execute_values  # type: ignore

# ---------------------------------------------------------------------------
# Configuration
#
# The following constants define defaults for API and database settings.
# They can be overridden via environment variables at runtime.  The
# management command sets these environment variables before calling
# ``run_once`` so that the ETL writes into the same PostgreSQL database
# configured in Django.

# API endpoint base for SurveyZen/KoboToolbox
HOST_BASE: str = os.getenv('HOST_BASE', 'https://panel.surveyzen.ir')
API_BASE: str = HOST_BASE.rstrip('/') + '/api/v2'

# TLS verification: can supply a custom CA bundle or disable verification
VERIFY_TLS: bool = os.getenv('VERIFY_TLS', 'True').lower() not in ('false', '0', 'no')
CUSTOM_CA: Optional[str] = os.getenv('CUSTOM_CA', None)
HTTP_TIMEOUT_SEC: int = int(os.getenv('HTTP_TIMEOUT_SEC', '60'))
# Interval between syncs when running in loop mode (unused here)
RUN_EVERY_SECONDS: int = int(os.getenv('RUN_EVERY_SECONDS', '600'))

# PostgreSQL connection details (override via environment vars in management command)
PG_HOST: str = os.getenv('PG_HOST', '127.0.0.1')
PG_PORT: int = int(os.getenv('PG_PORT', '5432'))
PG_DBNAME: str = os.getenv('PG_DBNAME', 'Temp_BAP')
PG_USER: str = os.getenv('PG_USER', 'postgres')
PG_PASSWORD: str = os.getenv('PG_PASSWORD', '123456789')

# Diagnostics configuration
RUN_NULL_AUDIT: bool = os.getenv('RUN_NULL_AUDIT', 'True').lower() not in ('false', '0', 'no')
AUTO_DROP_EMPTY_DUP_REPEAT_COLS: bool = os.getenv('AUTO_DROP_EMPTY_DUP_REPEAT_COLS', 'True').lower() not in ('false', '0', 'no')

# ---------------------------------------------------------------------------
# Logging
#
def setup_logger() -> logging.Logger:
    """Initialise a rotating logger for ETL runs."""
    logger = logging.getLogger("kobo_etl_generic")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    fh = logging.handlers.RotatingFileHandler(
        "etl_generic.log", maxBytes=8_000_000, backupCount=4, encoding="utf-8"
    )
    fh.setLevel(logging.INFO)
    fh.setFormatter(fmt)
    logger.addHandler(ch)
    logger.addHandler(fh)
    return logger

log = setup_logger()

# ---------------------------------------------------------------------------
# Helper functions and constants

PG_IDENT_MAX = 63  # PostgreSQL NAMEDATALEN-1

def verify_param() -> Any:
    """Return TLS verification parameter for requests."""
    return CUSTOM_CA if CUSTOM_CA else VERIFY_TLS

def kpi_session(api_token: str) -> requests.Session:
    """Create a requests Session with the Authorization header."""
    s = requests.Session()
    s.headers.update({"Authorization": f"Token {api_token}", "Accept": "application/json"})
    return s

def base_type(xls_type: str) -> str:
    if not xls_type:
        return ""
    return str(xls_type).strip().split()[0]

def map_xls_to_pg(xls_type: str) -> str:
    """Map XLSForm field types to PostgreSQL column types."""
    t = base_type(xls_type)
    if t == "integer":
        return "INTEGER"
    if t in ("decimal", "number", "range"):
        return "NUMERIC"
    if t == "date":
        return "DATE"
    if t == "time":
        return "TIME WITHOUT TIME ZONE"
    if t in ("start", "end"):
        return "TIMESTAMP WITHOUT TIME ZONE"
    return "TEXT"

def _norm_name(x: str) -> str:
    return re.sub(r"[\s,;؛،]+$", "", str(x).strip())

def sanitize_identifier_raw(path: str) -> str:
    """Sanitise arbitrary strings into PostgreSQL-safe identifiers."""
    name = path.replace("/", "__")
    name = re.sub(r"[^A-Za-z0-9_]+", "_", name)
    if re.match(r"^[0-9]", name):
        name = "c_" + name
    return name.lower()

def truncate_pg_ident(ident: str) -> str:
    if len(ident) <= PG_IDENT_MAX:
        return ident
    cut = ident[:PG_IDENT_MAX]
    log.debug(f"[ident] truncated '{ident}' -> '{cut}'")
    return cut

def sanitize_identifier(path: str) -> str:
    return truncate_pg_ident(sanitize_identifier_raw(path))

def split_path(p: str) -> List[str]:
    return [seg for seg in p.split("/") if seg]

# ---------------------------------------------------------------------------
# XLSForm parsing
#
def parse_xls_full_paths(xls_path: str) -> Tuple[List[Tuple[str, str]], Dict[str, List[Tuple[str, str]]]]:
    """Parse an XLSForm and return lists of (full_path, pg_type) pairs."""
    xls = pd.ExcelFile(xls_path)
    # Find a sheet with columns 'type' and 'name'
    sheet_name = "survey"
    if sheet_name not in xls.sheet_names:
        chosen: Optional[str] = None
        for sh in xls.sheet_names:
            df = xls.parse(sh)
            lc = [str(c).strip().lower() for c in df.columns]
            if "type" in lc and "name" in lc:
                chosen = sh
                break
        sheet_name = chosen or xls.sheet_names[0]
    survey = xls.parse(sheet_name).fillna("")
    survey.columns = [str(c).strip().lower() for c in survey.columns]

    stack: List[str] = []
    repeat_stack: List[str] = []
    repeats_set: set[str] = set()
    main_cols: List[Tuple[str, str]] = []
    rep_cols: Dict[str, List[Tuple[str, str]]] = {}

    def current_path() -> str:
        return "/".join(stack) if stack else ""

    for _, row in survey.iterrows():
        typ = str(row.get("type", "")).strip()
        nm = str(row.get("name", "")).strip()
        bt = base_type(typ)

        if bt == "begin_group":
            stack.append(_norm_name(nm))
            continue
        if bt == "end_group":
            if stack:
                stack.pop()
            continue
        if bt == "begin_repeat":
            stack.append(_norm_name(nm))
            rp = current_path()
            repeats_set.add(rp)
            repeat_stack.append(rp)
            continue
        if bt == "end_repeat":
            if repeat_stack:
                repeat_stack.pop()
            if stack:
                stack.pop()
            continue
        if not nm:
            continue
        if bt == "note":
            continue
        pg_type = map_xls_to_pg(typ)
        path = "/".join([*stack, nm]) if stack else nm
        if repeat_stack:
            root = repeat_stack[-1]
            rep_cols.setdefault(root, []).append((path, pg_type))
        else:
            main_cols.append((path, pg_type))
    for root in repeats_set:
        rep_cols.setdefault(root, [])
    return main_cols, rep_cols

# ---------------------------------------------------------------------------
# Database helpers
#
def pg_connect() -> psycopg2.extensions.connection:
    """Establish a connection to PostgreSQL using the latest environment variables.

    The ETL can run in different contexts.  When called from the Django
    management command, the command temporarily sets the ``PG_HOST``,
    ``PG_PORT``, ``PG_DBNAME``, ``PG_USER`` and ``PG_PASSWORD`` environment
    variables to mirror the settings of the InsightZen application
    database.  Import‑time constants (``PG_HOST``, ``PG_PORT``, etc.) are
    therefore *not* reliable if environment variables have been updated
    after import.  This helper reads the connection parameters from
    ``os.environ`` at call time so that the most recent values are
    honoured.  If an environment variable is missing, it falls back to
    the module‑level default for backward compatibility.

    Returns:
        psycopg2.extensions.connection: A new connection configured with
        the latest environment variables.
    """
    # Resolve parameters from environment on every call.  Use defaults
    # defined at module level if the environment variable is unset.
    host = os.environ.get('PG_HOST', PG_HOST)
    port = int(os.environ.get('PG_PORT', str(PG_PORT)))
    dbname = os.environ.get('PG_DBNAME', PG_DBNAME)
    user = os.environ.get('PG_USER', PG_USER)
    password = os.environ.get('PG_PASSWORD', PG_PASSWORD)
    return psycopg2.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=password,
    )

SYS_FIELDS_MAIN = [
    ("_id", "BIGINT"),
    ("_uuid", "TEXT"),
    ("_submission_time", "TIMESTAMP WITHOUT TIME ZONE"),
    ("_status", "TEXT"),
    ("__version__", "TEXT"),
    ("_submitted_by", "TEXT"),
    ("_xform_id_string", "TEXT"),
    ("_tags", "TEXT"),
    ("_notes", "TEXT"),
    ("_attachments", "TEXT"),
    ("_geolocation", "TEXT"),
    ("formhub/uuid", "TEXT"),
    ("meta/instanceID", "TEXT"),
    ("meta/rootUUID", "TEXT"),
]

SYS_MAIN_SANITIZED = {sanitize_identifier(x) for x, _ in SYS_FIELDS_MAIN}

def ensure_main_table(conn, table: str, main_cols: List[Tuple[str, str]]) -> None:
    """Create the main table if it does not exist."""
    with conn.cursor() as cur:
        seen: set[str] = set()
        items: List[Any] = []
        for nm, typ in SYS_FIELDS_MAIN + main_cols:
            cn = sanitize_identifier(nm)
            if cn in seen:
                continue
            seen.add(cn)
            # Compose column definition using sql.Identifier and sql.SQL for safety
            items.append(sql.SQL("{} {}").format(sql.Identifier(cn), sql.SQL(typ)))
        items.append(sql.SQL("PRIMARY KEY ({})").format(sql.Identifier("_id")))
        cur.execute(
            sql.SQL("CREATE TABLE IF NOT EXISTS {} ({})").format(sql.Identifier(table), sql.SQL(", ").join(items))
        )
    conn.commit()

def ensure_repeat_table(conn, table: str, repeat_cols: List[Tuple[str, str]]) -> None:
    """Create a repeat table if it does not exist."""
    with conn.cursor() as cur:
        seen: set[str] = set()
        items: List[Any] = []
        items.append(sql.SQL("{} {}").format(sql.Identifier("_submission_id"), sql.SQL("BIGINT")))
        items.append(sql.SQL("{} {}").format(sql.Identifier("repeat_index"), sql.SQL("INTEGER")))
        for nm, typ in repeat_cols:
            cn = sanitize_identifier(nm)
            if cn in seen:
                continue
            seen.add(cn)
            items.append(sql.SQL("{} {}").format(sql.Identifier(cn), sql.SQL(typ)))
        items.append(
            sql.SQL("PRIMARY KEY ({}, {})").format(sql.Identifier("_submission_id"), sql.Identifier("repeat_index"))
        )
        cur.execute(
            sql.SQL("CREATE TABLE IF NOT EXISTS {} ({})").format(sql.Identifier(table), sql.SQL(", ").join(items))
        )
    conn.commit()

def add_missing_columns(conn, table: str, cols: List[str]) -> None:
    """Ensure the given columns exist on a table (adding them as TEXT)."""
    if not cols:
        return
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            """,
            (table,),
        )
        existing = {r[0] for r in cur.fetchall()}
        new_cols: List[str] = []
        for raw in cols:
            candidate = sanitize_identifier(raw)
            if candidate in existing:
                continue
            cur.execute(
                sql.SQL("ALTER TABLE {} ADD COLUMN {} TEXT").format(
                    sql.Identifier(table), sql.Identifier(candidate)
                )
            )
            new_cols.append(candidate)
        if new_cols:
            log.info(f"[db] added columns to {table}: {new_cols}")
    conn.commit()

def get_max_main_id(conn, table: str) -> int:
    """Return the maximum _id currently in the main table."""
    with conn.cursor() as cur:
        cur.execute(sql.SQL("SELECT COALESCE(MAX({}), 0) FROM {} ").format(sql.Identifier("_id"), sql.Identifier(table)))
        (mx,) = cur.fetchone()
        return int(mx or 0)

def normalize_value(v: Any) -> Any:
    """Convert various types into database-storable values."""
    if v is None or v == "":
        return None
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, (bytes, bytearray)):
        try:
            return v.decode("utf-8", errors="ignore")
        except Exception:
            return str(v)
    return v

def to_sanitized_row(flat: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitise all keys in a dictionary and normalise values."""
    return {sanitize_identifier(k): normalize_value(v) for k, v in flat.items()}

def insert_many(conn, table: str, rows: List[Dict[str, Any]], conflict_cols: List[str]) -> None:
    """Insert a batch of rows with ON CONFLICT DO NOTHING."""
    if not rows:
        return
    all_cols: set[str] = set()
    for r in rows:
        all_cols |= set(r.keys())
    add_missing_columns(conn, table, list(all_cols))
    cols = sorted(all_cols)
    values = [tuple(r.get(c) for c in cols) for r in rows]
    q = sql.SQL("INSERT INTO {} ({}) VALUES %s ON CONFLICT ({}) DO NOTHING").format(
        sql.Identifier(table),
        sql.SQL(", ").join([sql.Identifier(c) for c in cols]),
        sql.SQL(", ").join([sql.Identifier(sanitize_identifier(c)) for c in conflict_cols]),
    )
    with conn.cursor() as cur:
        execute_values(cur, q.as_string(conn), values)
    conn.commit()

# ---------------------------------------------------------------------------
# API helpers

def get_asset_detail(session: requests.Session, asset_uid: str) -> Dict[str, Any]:
    """Fetch metadata about an asset (survey form)."""
    for path in (f"/assets/{asset_uid}.json", f"/assets/{asset_uid}/?format=json"):
        url = API_BASE.rstrip("/") + path
        r = session.get(url, timeout=HTTP_TIMEOUT_SEC, verify=verify_param())
        if r.status_code == 200:
            try:
                return r.json()
            except Exception:
                pass
    r.raise_for_status()
    return {}

def get_data_url_from_asset(asset_detail: Dict[str, Any], asset_uid: str) -> str:
    data_url = asset_detail.get("data")
    if data_url:
        if not data_url.endswith("/"):
            data_url += "/"
        return data_url
    return API_BASE.rstrip("/") + f"/assets/{asset_uid}/data/"

def fetch_new_submissions(session: requests.Session, data_url: str, last_id: int, label: str) -> Iterator[Dict[str, Any]]:
    """Yield new submission records from the API after the given _id."""
    params: Dict[str, Any] = {
        "format": "json",
        "query": json.dumps({"_id": {"$gt": last_id}}),
        "sort": json.dumps({"_id": 1}),
        "limit": 1000,
    }
    url = data_url
    total = 0
    page = 0
    t0 = time.time()
    while True:
        page += 1
        r = session.get(
            url,
            params=params if url == data_url else None,
            timeout=HTTP_TIMEOUT_SEC,
            verify=verify_param(),
        )
        r.raise_for_status()
        data = r.json()
        results = data.get("results", [])
        total += len(results)
        log.info(f"[api][{label}] page={page} fetched={len(results)}")
        for rec in results:
            yield rec
        next_url = data.get("next")
        if not next_url:
            break
        url = next_url
    dt = time.time() - t0
    log.info(f"[api][{label}] total fetched={total} in {dt:.2f}s")

# ---------------------------------------------------------------------------
# Data transformation

def flatten(d: Dict[str, Any], parent: str = "", sep: str = "/") -> Dict[str, Any]:
    """Flatten nested dictionaries into a single-level dict with slash-separated keys."""
    items: List[Tuple[str, Any]] = []
    for k, v in d.items():
        nk = f"{parent}{sep}{k}" if parent else k
        if isinstance(v, dict):
            items.extend(flatten(v, nk, sep=sep).items())
        else:
            items.append((nk, v))
    return dict(items)

def last_segment(path: str) -> str:
    """Return the last segment of a slash-separated path."""
    segs = split_path(path)
    return segs[-1] if segs else path

def prepare_rows_for_form(
    sub: Dict[str, Any],
    repeat_roots: List[str],
    label: str,
) -> Tuple[Dict[str, Any], Dict[str, List[Dict[str, Any]]]]:
    """
    Transform a single submission into a main row and repeat rows.

    Returns a tuple:
      - main_row: a sanitized dictionary for the main table
      - repeat_rows_by_root: mapping of repeat root path to list of sanitized rows
    """
    sub_copy = dict(sub)
    repeat_rows_by_root: Dict[str, List[Dict[str, Any]]] = {}
    for root in repeat_roots:
        tail = last_segment(root)
        arr = sub_copy.pop(tail, None) or sub_copy.pop(tail + ",", None) or []
        rows: List[Dict[str, Any]] = []
        for idx, item in enumerate(arr, start=1):
            flat = flatten(item)
            full: Dict[str, Any] = {}
            for k, v in flat.items():
                head = k.split("/", 1)[0]
                if _norm_name(head).lower() != _norm_name(tail).lower():
                    k = f"{tail}/{k}"
                if root != tail and (k.startswith(tail + "/") or k == tail):
                    k = root + k[len(tail) :]
                full[k] = v
            full["_submission_id"] = sub.get("_id")
            full["repeat_index"] = idx
            rows.append(to_sanitized_row(full))
        repeat_rows_by_root[root] = rows
    main_row_flat = flatten(sub_copy)
    main_row = to_sanitized_row(main_row_flat)
    return main_row, repeat_rows_by_root

# ---------------------------------------------------------------------------
# Diagnostics

def schema_mismatch_report(
    definition_main_cols: List[Tuple[str, str]],
    definition_repeat_cols: Dict[str, List[Tuple[str, str]]],
    main_table: str,
    sample_main_keys: set[str],
    sample_rep_keys_by_root: Dict[str, set[str]],
) -> None:
    """
    Compare sample keys against the form definition and log mismatches.
    """
    definition_main = {sanitize_identifier(p) for p, _ in definition_main_cols}
    only_in_definition_main = sorted(list(definition_main - sample_main_keys))[:50]
    only_in_data_main = sorted(list((sample_main_keys - definition_main) - SYS_MAIN_SANITIZED))[:50]
    if only_in_definition_main:
        log.warning(f"[schema][{main_table}] main: in definition not in sample: {only_in_definition_main}")
    if only_in_data_main:
        log.warning(f"[schema][{main_table}] main: in sample not in definition: {only_in_data_main}")
    for root, cols in definition_repeat_cols.items():
        definition_rep = {sanitize_identifier(p) for p, _ in cols}
        sample_rep = sample_rep_keys_by_root.get(root, set())
        only_in_definition_rep = sorted(list(definition_rep - sample_rep))[:50]
        only_in_data_rep = sorted(list(sample_rep - definition_rep))[:50]
        if only_in_definition_rep:
            log.warning(f"[schema][{main_table}] repeat[{root}]: in definition not in sample: {only_in_definition_rep}")
        if only_in_data_rep:
            log.warning(f"[schema][{main_table}] repeat[{root}]: in sample not in definition: {only_in_data_rep}")

def audit_all_null_columns(conn, table: str, max_cols: int = 200) -> None:
    """Log columns that have no non-null values in the given table."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='public' AND table_name=%s
            ORDER BY ordinal_position
            """,
            (table,),
        )
        cols = [r[0] for r in cur.fetchall()]
    skip = {"_id", "_submission_id", "repeat_index"}
    checked = 0
    for col in cols:
        if col in skip:
            continue
        with conn.cursor() as cur:
            cur.execute(sql.SQL('SELECT COUNT(*) FILTER (WHERE {} IS NOT NULL) FROM {}').format(sql.Identifier(col), sql.Identifier(table)))
            (nnz,) = cur.fetchone()
        if nnz == 0:
            log.warning(f"[audit] column {table}.{col} has 0 non-null values")
        checked += 1
        if checked >= max_cols:
            break

def cleanup_duplicate_repeat_columns(conn, table: str, repeat_prefix: str) -> None:
    """Drop duplicate repeat columns that are entirely NULL."""
    if not AUTO_DROP_EMPTY_DUP_REPEAT_COLS:
        return
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='public' AND table_name=%s
            """,
            (table,),
        )
        cols = [r[0] for r in cur.fetchall()]
    candidates: List[str] = []
    for col in cols:
        if col in ("_submission_id", "repeat_index"):
            continue
        if col.startswith(repeat_prefix):
            continue
        prefixed = repeat_prefix + col
        if prefixed in cols:
            with conn.cursor() as cur:
                cur.execute(sql.SQL('SELECT COUNT(*) FILTER (WHERE {} IS NOT NULL) FROM {}').format(sql.Identifier(col), sql.Identifier(table)))
                (nnz,) = cur.fetchone()
            if nnz == 0:
                candidates.append(col)
    if candidates:
        with conn.cursor() as cur:
            for col in candidates:
                cur.execute(sql.SQL("ALTER TABLE {} DROP COLUMN {};").format(sql.Identifier(table), sql.Identifier(col)))
        conn.commit()
        log.info(f"[cleanup] dropped empty duplicate cols from {table}: {candidates}")

# ---------------------------------------------------------------------------
# Core ETL logic

def extract_schema_from_asset(asset_detail: Dict[str, Any]) -> Tuple[List[Tuple[str, str]], Dict[str, List[Tuple[str, str]]]]:
    """Derive main and repeat column definitions from an asset payload."""
    if not isinstance(asset_detail, dict):
        raise ValueError("Asset detail payload is missing or invalid.")

    content = asset_detail.get("content")
    if isinstance(content, dict):
        survey_nodes = content.get("survey") or content.get("children") or []
    elif isinstance(content, list):
        survey_nodes = content
    else:
        survey_nodes = []
    if not isinstance(survey_nodes, list):
        survey_nodes = []

    main_cols: List[Tuple[str, str]] = []
    repeat_cols: Dict[str, List[Tuple[str, str]]] = {}

    def dedupe(items: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
        seen: set[str] = set()
        result: List[Tuple[str, str]] = []
        for name, typ in items:
            key = sanitize_identifier(name)
            if key in seen:
                continue
            seen.add(key)
            result.append((name, typ))
        return result

    def walk(nodes: List[Dict[str, Any]], parent_parts: List[str], repeat_key: Optional[str]) -> None:
        for node in nodes or []:
            if not isinstance(node, dict):
                continue
            node_type = str(node.get("type") or "").strip()
            node_name = (node.get("name") or "").strip()
            children = node.get("children") or []
            node_base = base_type(node_type)
            if node_base in {"begin_group", "group"}:
                next_parent = parent_parts + ([node_name] if node_name else [])
                walk(children, next_parent, repeat_key)
                continue
            if node_base == "begin_repeat":
                repeat_parts = parent_parts + ([node_name] if node_name else [])
                repeat_label_parts = [part for part in repeat_parts if part]
                repeat_label = "/".join(repeat_label_parts) or node_name or "repeat"
                repeat_cols.setdefault(repeat_label, [])
                walk(children, repeat_parts, repeat_label)
                continue
            if node_base.startswith("end"):
                continue
            if not node_name:
                continue
            path_parts = parent_parts + [node_name]
            full_path = "/".join([p for p in path_parts if p]) or node_name
            sql_type = map_xls_to_pg(node_type)
            if repeat_key:
                repeat_cols.setdefault(repeat_key, []).append((full_path, sql_type))
            else:
                main_cols.append((full_path, sql_type))
            if children:
                walk(children, path_parts, repeat_key)

    walk(survey_nodes, [], None)
    main_cols = dedupe(main_cols)
    for key, cols in list(repeat_cols.items()):
        repeat_cols[key] = dedupe(cols)

    if not main_cols and not repeat_cols:
        raise ValueError("Asset definition did not contain any survey questions.")

    return main_cols, repeat_cols


@dataclass
class FormSpec:
    api_token: str
    asset_uid: str
    main_table: str
    asset_detail: Optional[Dict[str, Any]] = None
    definition_main_cols: List[Tuple[str, str]] = field(default_factory=list)
    definition_repeat_cols: Dict[str, List[Tuple[str, str]]] = field(default_factory=dict)

def ensure_tables_for_form(conn, form: FormSpec) -> Dict[str, str]:
    """Ensure the main and repeat tables exist for a form."""
    if not form.asset_detail:
        raise ValueError("FormSpec.asset_detail must be populated before ensuring tables.")
    main_cols, rep_cols = extract_schema_from_asset(form.asset_detail)
    form.definition_main_cols = main_cols
    form.definition_repeat_cols = rep_cols
    ensure_main_table(conn, form.main_table, form.definition_main_cols)
    repeat_map: Dict[str, str] = {}
    for root in form.definition_repeat_cols.keys():
        tail = root.split("/")[-1]
        rep_table = f"{form.main_table}__{sanitize_identifier(tail)}"
        ensure_repeat_table(conn, rep_table, form.definition_repeat_cols[root])
        repeat_map[root] = rep_table
    return repeat_map

def run_once(form: FormSpec) -> Tuple[int, int]:
    """
    Execute a single synchronisation run for the given form specification.

    Returns a tuple (inserted_main, inserted_repeats) indicating how
    many new rows were inserted into the main table and repeat tables.
    Any exceptions are propagated to the caller.  The caller should
    handle exceptions and update status accordingly.
    """
    conn = pg_connect()
    try:
        session = kpi_session(form.api_token)
        if not form.asset_detail:
            form.asset_detail = get_asset_detail(session, form.asset_uid)
        repeat_table_map = ensure_tables_for_form(conn, form)
        last_id = get_max_main_id(conn, form.main_table)
        log.info(f"[info][{form.main_table}] last _id = {last_id}")
        data_url = get_data_url_from_asset(form.asset_detail, form.asset_uid)
        log.info(f"[info][{form.main_table}] data endpoint: {data_url}")
        batch_main: List[Dict[str, Any]] = []
        batch_rep: Dict[str, List[Dict[str, Any]]] = {t: [] for t in repeat_table_map.values()}
        total_main = 0
        total_rep = 0
        sample_main_keys: set[str] = set()
        sample_rep_keys_by_root: Dict[str, set[str]] = {}
        sample_main_seen = 0
        sample_rep_seen: Dict[str, int] = {}
        repeat_roots_full = list(form.definition_repeat_cols.keys())
        label = f"{form.main_table}/{form.asset_uid}"
        for sub in fetch_new_submissions(session, data_url, last_id, label=label):
            main_row, rep_rows_by_root = prepare_rows_for_form(sub, repeat_roots_full, label=label)
            if sample_main_seen < 3:
                sample_main_keys |= set(main_row.keys())
                sample_main_seen += 1
            for root, rows in rep_rows_by_root.items():
                if not rows:
                    continue
                sample_rep_keys_by_root.setdefault(root, set())
                if sample_rep_seen.get(root, 0) < 3:
                    sample_rep_keys_by_root[root] |= set(rows[0].keys())
                    sample_rep_seen[root] = sample_rep_seen.get(root, 0) + 1
            batch_main.append(main_row)
            for root, rows in rep_rows_by_root.items():
                tbl = repeat_table_map.get(root)
                if tbl and rows:
                    batch_rep.setdefault(tbl, []).extend(rows)
            if len(batch_main) >= 1000:
                insert_many(conn, form.main_table, batch_main, conflict_cols=["_id"])
                total_main += len(batch_main)
                batch_main.clear()
                for tbl, rows in batch_rep.items():
                    if rows:
                        insert_many(conn, tbl, rows, conflict_cols=["_submission_id", "repeat_index"])
                        total_rep += len(rows)
                        batch_rep[tbl] = []
        if batch_main:
            insert_many(conn, form.main_table, batch_main, conflict_cols=["_id"])
            total_main += len(batch_main)
        for tbl, rows in batch_rep.items():
            if rows:
                insert_many(conn, tbl, rows, conflict_cols=["_submission_id", "repeat_index"])
                total_rep += len(rows)
        log.info(f"[done][{form.main_table}] inserted main={total_main}, repeat={total_rep}")
        schema_mismatch_report(
            form.definition_main_cols,
            form.definition_repeat_cols,
            form.main_table,
            sample_main_keys,
            sample_rep_keys_by_root,
        )
        if RUN_NULL_AUDIT:
            audit_all_null_columns(conn, form.main_table, max_cols=200)
            for root in form.definition_repeat_cols.keys():
                tbl = repeat_table_map.get(root)
                if tbl:
                    audit_all_null_columns(conn, tbl, max_cols=200)
        for root in form.definition_repeat_cols.keys():
            tbl = repeat_table_map.get(root)
            if tbl:
                prefix = sanitize_identifier(root.split("/")[-1]) + "__"
                cleanup_duplicate_repeat_columns(conn, tbl, repeat_prefix=prefix)
        return total_main, total_rep
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# CLI support

def cli_main() -> None:
    """Entry point for running the ETL from the command line."""
    p = argparse.ArgumentParser(description="Kobo/SurveyZen ETL (single run)")
    p.add_argument("--api-token", required=True, help="API Token for Kobo/SurveyZen")
    p.add_argument("--asset-uid", required=True, help="Asset UID of the form")
    args = p.parse_args()
    table_name = sanitize_identifier(args.asset_uid)
    form = FormSpec(
        api_token=args.api_token,
        asset_uid=args.asset_uid,
        main_table=table_name,
    )
    inserted_main, inserted_rep = run_once(form)
    print(f"Inserted main={inserted_main}, repeats={inserted_rep}")

if __name__ == "__main__":
    cli_main()