# InsightZen Deployment Notes

The application reads environment variables for sensitive settings such as the
Django secret key and database connection details. Copy `.env.sample` to `.env`
for local development; it defaults to SQLite to keep local runs self-contained.
Production deployments should set the PostgreSQL variables directly in the
environment (or a secure secrets store) rather than committing real values.

| Setting | Environment variable | Notes |
| --- | --- | --- |
| Django secret key | `DJANGO_SECRET_KEY` | Required. Set per-environment; do not commit real values. |
| Debug mode | `DJANGO_DEBUG` | Defaults to `False`. Set to `True` in `.env` for local development only. |
| Database backend | `DATABASE_ENGINE` | Leave unset (or any value other than `postgres`) to use SQLite. Set to `postgres` (or set any `PG*` variable) to enable PostgreSQL. |
| Django DB host | `PGHOST` | Required when using PostgreSQL. |
| Django DB port | `PGPORT` | Optional; defaults to `5432` when using PostgreSQL. |
| Django DB user | `PGUSER` | Required when using PostgreSQL. |
| Django DB password | `PGPASSWORD` | Required when using PostgreSQL. |
| Django DB name | `PGDATABASE` | Required when using PostgreSQL. |
| Respondent DB host | `RESPONDENT_DB_HOST` | Set when syncing the respondent bank. |
| Respondent DB port | `RESPONDENT_DB_PORT` | Optional; defaults to `5432` for respondent DB connections. |
| Respondent DB user | `RESPONDENT_DB_USER` | Set when syncing the respondent bank. |
| Respondent DB password | `RESPONDENT_DB_PASSWORD` | Set when syncing the respondent bank. |
| Respondent DB name | `RESPONDENT_DB_NAME` | Set when syncing the respondent bank. |

Export these variables (for example via `.env` or your process manager) before
running the Django management commands. Leave `DJANGO_DEBUG` unset (the default
`False`) in production, and populate PostgreSQL variables only in the
environments that need them.

## Applying migrations on PostgreSQL deployments

Enable the built-in PostgreSQL helpers in Django by ensuring
`django.contrib.postgres` is in `INSTALLED_APPS` (already set in
`insightzen/settings.py`). When `DATABASE_ENGINE=postgres` (or any `PG*`
variable is set), Django will connect to PostgreSQL; otherwise it uses SQLite.
After updating deployments or local environments, run the migrations so Django
can perform system checks without errors:

```bash
python manage.py migrate
```

Run this command against every PostgreSQL-backed environment after deploying
changes or refreshing dependencies.

To change the primary application database connection, update the values in
`insightzen/settings.py` (or override them via the matching `PG*` environment
variables). The respondent bank sync uses separate defaults in
`core/data_load_utils.py`, which can also be overridden with the corresponding
`RESPONDENT_DB_*` environment variables.

## Loading the respondent bank

To populate the local `Person` and `Mobile` tables from the primary PostgreSQL
source, run the dedicated management command after applying migrations:

```bash
python manage.py import_respondent_bank  # add --no-input to skip confirmation
```

Pass `--force` if you need to import even when data already exists.
Ensure the `RESPONDENT_DB_*` environment variables (or the defaults in
`core/data_load_utils.py`) are set to the correct source database before running
`python manage.py import_respondent_bank`.

## Deployment sequence

Run the respondent bank import immediately after applying migrations and before
starting any application processes so `Person` and `Mobile` records are ready
when the app serves traffic. The helper scripts automatically load `.env` so the
migrations and import share the same PostgreSQL and respondent bank
configuration:

```bash
./scripts/deploy_migrate_and_import.sh
# then start your WSGI/ASGI workers
```

The helper scripts use `--no-input` so they can run non-interactively during
deployments. Override the database connection values via the environment if they
ever diverge from `.env`.
