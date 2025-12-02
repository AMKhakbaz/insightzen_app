# InsightZen Deployment Notes

The application now requires explicit environment variables for sensitive
settings such as the Django secret key and database connection details. Copy
`.env.sample` to `.env` for local development and adjust the values to match
your environment before running any management commands. If `.env` is absent,
the app automatically falls back to `.env.sample` values as a convenience, but
these defaults are insecure and should be replaced in real deployments.

| Setting | Environment variable | Notes |
| --- | --- | --- |
| Django secret key | `DJANGO_SECRET_KEY` | Required. Generate a unique value for each deployment. |
| Debug mode | `DJANGO_DEBUG` | Defaults to `False`. Set to `True` in `.env` for local development only. |
| Django DB host | `PGHOST` | Defaults to `185.204.171.78` if not set. |
| Django DB port | `PGPORT` | Defaults to `5433` if not set. |
| Django DB user | `PGUSER` | Defaults to `insightzen` if not set. |
| Django DB password | `PGPASSWORD` | Defaults to `K8RwWAPT5F7-?mrMBzR<` if not set. |
| Django DB name | `PGDATABASE` | Defaults to `insightzen3` if not set. |
| Respondent DB host | `RESPONDENT_DB_HOST` | Defaults to `185.204.171.78` if not set. |
| Respondent DB port | `RESPONDENT_DB_PORT` | Defaults to `5433` if not set. |
| Respondent DB user | `RESPONDENT_DB_USER` | Defaults to `insightzen` if not set. |
| Respondent DB password | `RESPONDENT_DB_PASSWORD` | Defaults to `K8RwWAPT5F7-?mrMBzR<` if not set. |
| Respondent DB name | `RESPONDENT_DB_NAME` | Defaults to `Numbers` if not set. |

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
