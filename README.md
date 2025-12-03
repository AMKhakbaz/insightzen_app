# InsightZen Deployment Notes

The application requires environment variables for sensitive settings such as the
Django secret key and database connection details. Copy `.env.sample` to `.env`
for local development, then replace every `CHANGE_ME` placeholder with your
actual secrets and connection parameters before running any management commands.
Provide real secrets via your environment (process manager, container runtime,
etc.) instead of committing them to source control.

| Setting | Environment variable | Notes |
| --- | --- | --- |
| Django secret key | `DJANGO_SECRET_KEY` | Required. Generate a unique value for each deployment (the sample file uses `CHANGE_ME`). |
| Debug mode | `DJANGO_DEBUG` | Defaults to `False`. Set to `True` in `.env` for local development only. |
| Django DB host | `PGHOST` | Set to your PostgreSQL host; the sample file uses `CHANGE_ME` and the app falls back to a legacy default if unset. |
| Django DB port | `PGPORT` | Set to your PostgreSQL port; defaults to `5433` if not set. |
| Django DB user | `PGUSER` | Set to your PostgreSQL user (the sample file uses `CHANGE_ME`). |
| Django DB password | `PGPASSWORD` | Set to your PostgreSQL password (the sample file uses `CHANGE_ME`). |
| Django DB name | `PGDATABASE` | Set to your PostgreSQL database name (the sample file uses `CHANGE_ME`). |
| Respondent DB host | `RESPONDENT_DB_HOST` | Set to your respondent source DB host; the sample file uses `CHANGE_ME` and the app falls back to a legacy default if unset. |
| Respondent DB port | `RESPONDENT_DB_PORT` | Set to your respondent source DB port; defaults to `5433` if not set. |
| Respondent DB user | `RESPONDENT_DB_USER` | Set to your respondent source DB user (the sample file uses `CHANGE_ME`). |
| Respondent DB password | `RESPONDENT_DB_PASSWORD` | Set to your respondent source DB password (the sample file uses `CHANGE_ME`). |
| Respondent DB name | `RESPONDENT_DB_NAME` | Set to your respondent source DB name (the sample file uses `CHANGE_ME`). |

Export these variables (for example via a `.env` file) before running the Django
management commands. Production environments should set real values via your
process manager or container orchestration rather than committing secrets to
source control. Leave `DJANGO_DEBUG` unset (the default `False`) in production
and only enable it locally when debugging.

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
