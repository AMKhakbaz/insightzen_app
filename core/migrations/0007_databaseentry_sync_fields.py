"""Migration for adding synchronisation tracking fields to DatabaseEntry.

This migration introduces two optional fields on the DatabaseEntry model:

* ``last_sync`` records the timestamp of the most recent synchronisation
  attempt.  This allows administrators to see when each external
  database was last updated.
* ``last_error`` stores the error message (if any) from the last
  synchronisation.  This is useful for debugging failures during the
  ETL process.  The field defaults to an empty string and is cleared
  whenever a synchronisation succeeds.

The migration depends on the previous migration that introduced the
DatabaseEntry model.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_databaseentry_xlsform_filefield'),
    ]

    operations = [
        migrations.AddField(
            model_name='databaseentry',
            name='last_sync',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='databaseentry',
            name='last_error',
            field=models.TextField(blank=True, default=''),
        ),
    ]