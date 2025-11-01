"""Alter xlsform field to FileField for DatabaseEntry.

This migration changes the xlsform attribute on the DatabaseEntry model
from a CharField to a FileField.  FileField stores uploaded files
within the ``xlsforms/`` directory of the MEDIA_ROOT.  The previous
CharField held the path or name of the XLSForm; migrating to a
FileField allows the application to accept uploaded XLSX files
directly from the user.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_membership_title_databaseentry_project_types'),
    ]

    operations = [
        migrations.AlterField(
            model_name='databaseentry',
            name='xlsform',
            field=models.FileField(max_length=255, upload_to='xlsforms/'),
        ),
    ]