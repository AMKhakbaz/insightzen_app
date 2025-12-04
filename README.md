# InsightZen Deployment Notes

The application requires environment variables for sensitive settings such as the
Django secret key and database connection details. A checked-in `.env` file
copied from `.env.sample` already contains the current PostgreSQL and respondent
bank connection values used in deployment. Update those values in `.env` when
rotating credentials, and export the file in your process manager or container
runtime before running any management commands.

| Setting | Environment variable | Notes |
| --- | --- | --- |
| Django secret key | `DJANGO_SECRET_KEY` | Required. The checked-in `.env` holds the current deployment value; update when rotating secrets. |
| Debug mode | `DJANGO_DEBUG` | Defaults to `False`. Set to `True` in `.env` for local development only. |
| Django DB host | `PGHOST` | Pre-populated in `.env` with the live PostgreSQL host; update if the host changes. |
| Django DB port | `PGPORT` | Pre-populated in `.env`; defaults to `5433` if not set. |
| Django DB user | `PGUSER` | Pre-populated in `.env` with the live PostgreSQL user. |
| Django DB password | `PGPASSWORD` | Pre-populated in `.env` with the live PostgreSQL password. |
| Django DB name | `PGDATABASE` | Pre-populated in `.env` with the live PostgreSQL database name. |
| Respondent DB host | `RESPONDENT_DB_HOST` | Pre-populated in `.env` with the live respondent source DB host. |
| Respondent DB port | `RESPONDENT_DB_PORT` | Pre-populated in `.env`; defaults to `5433` if not set. |
| Respondent DB user | `RESPONDENT_DB_USER` | Pre-populated in `.env` with the live respondent source DB user. |
| Respondent DB password | `RESPONDENT_DB_PASSWORD` | Pre-populated in `.env` with the live respondent source DB password. |
| Respondent DB name | `RESPONDENT_DB_NAME` | Pre-populated in `.env` with the live respondent source DB name. |

Export these variables (for example via `.env` or your process manager) before
running the Django management commands. Production environments should still
load the checked-in `.env` securely and leave `DJANGO_DEBUG` unset (the default
`False`) in production.

## Applying migrations on PostgreSQL deployments

Enable the built-in PostgreSQL helpers in Django by ensuring
`django.contrib.postgres` is in `INSTALLED_APPS` (already set in
`insightzen/settings.py`). After updating deployments or local environments, run
the migrations so Django can perform system checks without errors:

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
