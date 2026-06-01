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
| Database backend | `DATABASE_ENGINE` | Leave unset (or any value other than `postgres`) to use SQLite. Set to `postgres` (or set any application DB variable) to enable PostgreSQL. |
| Django DB host | `PGHOST` | Required when using PostgreSQL. Legacy aliases such as `PG_HOST`, `DB_HOST` and `POSTGRES_HOST` are also accepted. |
| Django DB port | `PGPORT` | Optional; defaults to `5432` when using PostgreSQL. Legacy aliases such as `PG_PORT`, `DB_PORT` and `POSTGRES_PORT` are also accepted. |
| Django DB user | `PGUSER` | Required when using PostgreSQL. Legacy aliases such as `PG_USER`, `DB_USER` and `POSTGRES_USER` are also accepted. |
| Django DB password | `PGPASSWORD` | Required when using PostgreSQL. Legacy aliases such as `PG_PASSWORD`, `DB_PASSWORD` and `POSTGRES_PASSWORD` are also accepted. |
| Django DB name | `PGDATABASE` | Required when using PostgreSQL. Legacy aliases such as `PG_DBNAME`, `PG_DB`, `DB_NAME` and `POSTGRES_DB` are also accepted. |
| Respondent DB host | `RESPONDENT_DB_HOST` | Set when syncing the respondent bank. |
| Respondent DB port | `RESPONDENT_DB_PORT` | Optional; defaults to `5432` for respondent DB connections. |
| Respondent DB user | `RESPONDENT_DB_USER` | Set when syncing the respondent bank. |
| Respondent DB password | `RESPONDENT_DB_PASSWORD` | Set when syncing the respondent bank. |
| Respondent DB name | `RESPONDENT_DB_NAME` | Set when syncing the respondent bank. |

Export these variables (for example via `.env` or your process manager) before
running the Django management commands. Leave `DJANGO_DEBUG` unset (the default
`False`) in production, and populate PostgreSQL variables only in the
environments that need them. During startup Django mirrors canonical `PGHOST`
values to the legacy `PG_HOST` style names (and vice versa) so settings,
management commands and ETL scripts all target the same database.

## Local Windows quick start

Use a virtual environment inside the repository so PowerShell activation and
subsequent package installs target the same Python environment:

```powershell
git clone git@github.com:AMKhakbaz/insightzen_app.git "$HOME\Desktop\insightzen_app"
cd "$HOME\Desktop\insightzen_app"
git fetch --all --prune
git switch v0.2.17
git pull --ff-only

python --version
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
python -m django --version
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

If you prefer to keep the environment outside the repository, create it as
`..\.venv` and activate it with `..\.venv\Scripts\Activate.ps1`. The create
and activate paths must match; otherwise PowerShell will keep using the global
Python installation.

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

To change the primary application database connection, update the matching
`PG*` environment variables (or their documented aliases). The respondent bank
sync uses the same application database by default; set the corresponding
`RESPONDENT_DB_*` environment variables only when that source lives in a
different PostgreSQL database.

## Loading the respondent bank

To populate the local `Person` and `Mobile` tables from the primary PostgreSQL
source, run the dedicated management command after applying migrations:

```bash
python manage.py import_respondent_bank  # add --no-input to skip confirmation
```

Pass `--force` if you need to import even when data already exists.
Ensure the application `PG*` variables are correct before running
`python manage.py import_respondent_bank`; if the respondent bank lives in a
different source database, set `RESPONDENT_DB_*` variables to override the
application connection for that import only.

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
