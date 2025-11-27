# InsightZen Deployment Notes

The application is configured to connect to the managed InsightZen PostgreSQL
instance by default.  Provide overrides via environment variables if you need to
point at a different database.

| Setting | Environment variable | Default |
| --- | --- | --- |
| Django DB host | `PGHOST` | `185.204.171.78` |
| Django DB port | `PGPORT` | `5433` |
| Django DB user | `PGUSER` | `insightzen` |
| Django DB password | `PGPASSWORD` | `K8RwWAPT5F7-?mrMBzR<` |
| Django DB name | `PGDATABASE` | `insightzen2` |
| Respondent DB host | `RESPONDENT_DB_HOST` | `185.204.171.78` |
| Respondent DB port | `RESPONDENT_DB_PORT` | `5433` |
| Respondent DB user | `RESPONDENT_DB_USER` | `insightzen` |
| Respondent DB password | `RESPONDENT_DB_PASSWORD` | `K8RwWAPT5F7-?mrMBzR<` |
| Respondent DB name | `RESPONDENT_DB_NAME` | `Numbers` |

Export any of these variables (for example via a `.env` file) before running the
Django management commands to override the defaults.

## Loading the respondent bank

To populate the local `Person` and `Mobile` tables from the primary PostgreSQL
source, run the dedicated management command after applying migrations:

```bash
python manage.py import_respondent_bank  # add --no-input to skip confirmation
```

Pass `--force` if you need to import even when data already exists.
