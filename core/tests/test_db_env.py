from django.test import SimpleTestCase

from insightzen.db_env import (
    mirror_pg_env_aliases,
    postgres_requested,
    primary_postgres_config,
    respondent_postgres_config,
)


class DatabaseEnvironmentTests(SimpleTestCase):
    def test_legacy_pg_names_request_postgres_and_build_primary_config(self):
        environ = {
            'PG_HOST': 'db.internal',
            'PG_PORT': '15432',
            'PG_DBNAME': 'insightzen',
            'PG_USER': 'app_user',
            'PG_PASSWORD': 'secret',
        }

        self.assertTrue(postgres_requested(environ))
        self.assertEqual(
            primary_postgres_config(environ),
            {
                'HOST': 'db.internal',
                'PORT': '15432',
                'NAME': 'insightzen',
                'USER': 'app_user',
                'PASSWORD': 'secret',
            },
        )

    def test_mirror_pg_env_aliases_populates_missing_canonical_and_legacy_names(self):
        environ = {
            'PG_HOST': 'legacy-host',
            'PGPORT': '5433',
            'PG_DBNAME': 'legacy-name',
            'PGUSER': 'canonical-user',
            'PG_PASSWORD': 'legacy-password',
        }

        mirror_pg_env_aliases(environ)

        self.assertEqual(environ['PGHOST'], 'legacy-host')
        self.assertEqual(environ['PG_PORT'], '5433')
        self.assertEqual(environ['PGDATABASE'], 'legacy-name')
        self.assertEqual(environ['PG_USER'], 'canonical-user')
        self.assertEqual(environ['PGPASSWORD'], 'legacy-password')

    def test_respondent_config_falls_back_to_primary_database_env(self):
        environ = {
            'PGHOST': 'app-db',
            'PGPORT': '5432',
            'PGDATABASE': 'app_name',
            'PGUSER': 'app_user',
            'PGPASSWORD': 'app_password',
        }

        self.assertEqual(
            respondent_postgres_config(environ),
            {
                'HOST': 'app-db',
                'PORT': '5432',
                'NAME': 'app_name',
                'USER': 'app_user',
                'PASSWORD': 'app_password',
            },
        )

    def test_respondent_config_prefers_respondent_specific_env(self):
        environ = {
            'PGHOST': 'app-db',
            'PGPORT': '5432',
            'PGDATABASE': 'app_name',
            'PGUSER': 'app_user',
            'PGPASSWORD': 'app_password',
            'RESPONDENT_DB_HOST': 'respondent-db',
            'RESPONDENT_DB_PORT': '6543',
            'RESPONDENT_DB_NAME': 'respondents',
            'RESPONDENT_DB_USER': 'respondent_user',
            'RESPONDENT_DB_PASSWORD': 'respondent_password',
        }

        self.assertEqual(
            respondent_postgres_config(environ),
            {
                'HOST': 'respondent-db',
                'PORT': '6543',
                'NAME': 'respondents',
                'USER': 'respondent_user',
                'PASSWORD': 'respondent_password',
            },
        )
