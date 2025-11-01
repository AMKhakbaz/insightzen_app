from django.db import migrations


class Migration(migrations.Migration):
    """Remove the address field from the Person model.

    This migration drops the ``address`` column from the ``core_person``
    table.  The address was deemed unnecessary for performance reasons
    when loading and querying millions of records.  Existing
    applications should ensure that any data in this column has been
    migrated or is no longer needed prior to applying this migration.
    """

    dependencies = [
        ('core', '0003_start_end_form'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='person',
            name='address',
        ),
    ]