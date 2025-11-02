from django.db import migrations


def purge_xlsform_files(apps, schema_editor):
    DatabaseEntry = apps.get_model('core', 'DatabaseEntry')
    for entry in DatabaseEntry.objects.all():
        file_field = getattr(entry, 'xlsform', None)
        if not file_field:
            continue
        try:
            file_field.delete(save=False)
        except Exception:
            # Ignore storage errors so the schema migration can proceed.
            pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_databaseentry_sync_fields'),
    ]

    operations = [
        migrations.RunPython(purge_xlsform_files, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='databaseentry',
            name='xlsform',
        ),
    ]
