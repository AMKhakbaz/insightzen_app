# InsightZen Deployment Notes

The application now requires explicit environment variables for sensitive
settings such as the Django secret key and database connection details. Copy
`.env.sample` to `.env` for local development and adjust the values to match
your environment before running any management commands.

| Setting | Environment variable | Notes |
| --- | --- | --- |
| Django secret key | `DJANGO_SECRET_KEY` | Required. Generate a unique value for each deployment. |
| Debug mode | `DJANGO_DEBUG` | Defaults to `False`. Set to `True` in `.env` for local development only. |
| Django DB host | `PGHOST` | Required. Example: `localhost` for local development. |
| Django DB port | `PGPORT` | Required. Example: `5432`. |
| Django DB user | `PGUSER` | Defaults to `insightzen` if not set. |
| Django DB password | `PGPASSWORD` | Required. |
| Django DB name | `PGDATABASE` | Defaults to `insightzen3` if not set. |
| Respondent DB host | `RESPONDENT_DB_HOST` | Defaults to `localhost` in `.env.sample`. |
| Respondent DB port | `RESPONDENT_DB_PORT` | Defaults to `5432` in `.env.sample`. |
| Respondent DB user | `RESPONDENT_DB_USER` | Defaults to `insightzen` in `.env.sample`. |
| Respondent DB password | `RESPONDENT_DB_PASSWORD` | Defaults to `please-change-me` in `.env.sample`. |
| Respondent DB name | `RESPONDENT_DB_NAME` | Defaults to `Numbers` in `.env.sample`. |

Export these variables (for example via a `.env` file) before running the Django
management commands. Production environments should set real values via your
process manager or container orchestration rather than committing secrets to
source control. Leave `DJANGO_DEBUG` unset (the default `False`) in production
and only enable it locally when debugging.

## Loading the respondent bank

To populate the local `Person` and `Mobile` tables from the primary PostgreSQL
source, run the dedicated management command after applying migrations:

```bash
python manage.py import_respondent_bank  # add --no-input to skip confirmation
```

Pass `--force` if you need to import even when data already exists.
