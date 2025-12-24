"""Add PostgreSQL source fields to DatabaseEntry."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0022_databaseentry_source_type_databaseentry_upload_file_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='databaseentry',
            name='db_database',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='databaseentry',
            name='db_host',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='databaseentry',
            name='db_password',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='databaseentry',
            name='db_port',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='databaseentry',
            name='db_table',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='databaseentry',
            name='db_username',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
