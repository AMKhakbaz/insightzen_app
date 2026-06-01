"""Database environment helpers for InsightZen.

The deployment history of this project used both libpq-style names
(``PGHOST``/``PGDATABASE``) and script-style names
(``PG_HOST``/``PG_DBNAME``).  Keep all database consumers aligned by
resolving both spellings in one place and preferring the explicit Django
/libpq variables when both are present.
"""

from __future__ import annotations

import os
from typing import Iterable, Mapping, MutableMapping

TRUTHY_VALUES = {"1", "true", "yes", "on"}
POSTGRES_ENGINES = {"postgres", "postgresql", "django.db.backends.postgresql"}

DB_HOST_ENV = ("PGHOST", "PG_HOST", "DB_HOST", "POSTGRES_HOST")
DB_PORT_ENV = ("PGPORT", "PG_PORT", "DB_PORT", "POSTGRES_PORT")
DB_NAME_ENV = ("PGDATABASE", "PG_DBNAME", "PG_DB", "DB_NAME", "POSTGRES_DB")
DB_USER_ENV = ("PGUSER", "PG_USER", "DB_USER", "POSTGRES_USER")
DB_PASSWORD_ENV = ("PGPASSWORD", "PG_PASSWORD", "DB_PASSWORD", "POSTGRES_PASSWORD")

DB_ENV_ALIASES: Mapping[str, tuple[str, ...]] = {
    "HOST": DB_HOST_ENV,
    "PORT": DB_PORT_ENV,
    "NAME": DB_NAME_ENV,
    "USER": DB_USER_ENV,
    "PASSWORD": DB_PASSWORD_ENV,
}

RESPONDENT_DB_ENV_ALIASES: Mapping[str, tuple[str, ...]] = {
    "HOST": ("RESPONDENT_DB_HOST", *DB_HOST_ENV),
    "PORT": ("RESPONDENT_DB_PORT", *DB_PORT_ENV),
    "NAME": ("RESPONDENT_DB_NAME", *DB_NAME_ENV),
    "USER": ("RESPONDENT_DB_USER", *DB_USER_ENV),
    "PASSWORD": ("RESPONDENT_DB_PASSWORD", *DB_PASSWORD_ENV),
}

CANONICAL_TO_LEGACY_PG = {
    "PGHOST": "PG_HOST",
    "PGPORT": "PG_PORT",
    "PGDATABASE": "PG_DBNAME",
    "PGUSER": "PG_USER",
    "PGPASSWORD": "PG_PASSWORD",
}
LEGACY_TO_CANONICAL_PG = {value: key for key, value in CANONICAL_TO_LEGACY_PG.items()}


def env_value(names: Iterable[str], default: str | None = None, environ: Mapping[str, str] | None = None) -> str | None:
    """Return the first non-empty environment value from ``names``."""

    source = os.environ if environ is None else environ
    for name in names:
        value = source.get(name)
        if value not in (None, ""):
            return value
    return default


def env_bool(name: str, default: bool = False, environ: Mapping[str, str] | None = None) -> bool:
    value = (os.environ if environ is None else environ).get(name)
    if value is None:
        return default
    return value.strip().lower() in TRUTHY_VALUES


def mirror_pg_env_aliases(environ: MutableMapping[str, str] | None = None) -> None:
    """Populate missing PG alias names so subprocesses and scripts agree."""

    target = os.environ if environ is None else environ
    for canonical, legacy in CANONICAL_TO_LEGACY_PG.items():
        canonical_value = target.get(canonical)
        legacy_value = target.get(legacy)
        if canonical_value and not legacy_value:
            target[legacy] = canonical_value
        elif legacy_value and not canonical_value:
            target[canonical] = legacy_value


def postgres_requested(environ: Mapping[str, str] | None = None) -> bool:
    """Return whether the primary application DB should be PostgreSQL."""

    source = os.environ if environ is None else environ
    engine = source.get("DATABASE_ENGINE", "").strip().lower()
    return (
        engine in POSTGRES_ENGINES
        or source.get("USE_POSTGRES", "").strip().lower() in TRUTHY_VALUES
        or any(env_value(aliases, environ=source) for aliases in DB_ENV_ALIASES.values())
    )


def require_env_value(label: str, names: Iterable[str], environ: Mapping[str, str] | None = None) -> str:
    value = env_value(names, environ=environ)
    if value:
        return value
    names_display = "/".join(names)
    raise RuntimeError(f"Set {names_display} for {label} (see .env.sample).")


def primary_postgres_config(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """Build a PostgreSQL config dict from all supported env aliases."""

    source = os.environ if environ is None else environ
    return {
        "HOST": env_value(DB_HOST_ENV, "localhost", source) or "localhost",
        "PORT": env_value(DB_PORT_ENV, "5432", source) or "5432",
        "NAME": require_env_value("the application database name", DB_NAME_ENV, source),
        "USER": require_env_value("the application database user", DB_USER_ENV, source),
        "PASSWORD": require_env_value("the application database password", DB_PASSWORD_ENV, source),
    }


def respondent_postgres_config(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """Build respondent-bank DB config, falling back to the primary PG env."""

    source = os.environ if environ is None else environ
    return {
        "HOST": env_value(RESPONDENT_DB_ENV_ALIASES["HOST"], "localhost", source) or "localhost",
        "PORT": env_value(RESPONDENT_DB_ENV_ALIASES["PORT"], "5432", source) or "5432",
        "NAME": require_env_value("the respondent database name", RESPONDENT_DB_ENV_ALIASES["NAME"], source),
        "USER": require_env_value("the respondent database user", RESPONDENT_DB_ENV_ALIASES["USER"], source),
        "PASSWORD": require_env_value("the respondent database password", RESPONDENT_DB_ENV_ALIASES["PASSWORD"], source),
    }
