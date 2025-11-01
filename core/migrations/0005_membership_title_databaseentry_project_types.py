"""Migration to add membership title, database entry model, and replace
project type with types ArrayField.

This migration reflects structural changes requested by the user.  It
adds a ``title`` field to the ``Membership`` model so that each
membership record can include a descriptive label.  It introduces a
``DatabaseEntry`` model for managing external database connections.  It
also removes the old ``type`` field from ``Project`` and replaces it
with a PostgreSQL ``ArrayField`` called ``types``.  These changes
depend on the previous migration which dropped the ``address`` field
from ``Person``.
"""

from __future__ import annotations

from django.db import migrations, models
import django.contrib.postgres.fields
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0004_drop_person_address"),
    ]

    operations = [
        # Add a title field to Membership.  This is optional and can be
        # null or blank.
        migrations.AddField(
            model_name="membership",
            name="title",
            field=models.CharField(max_length=100, null=True, blank=True),
        ),
        # Remove the old 'type' field from Project if it exists.  This
        # field stored a single type; we replace it with 'types' below.
        migrations.RemoveField(
            model_name="project",
            name="type",
        ),
        # Add a new 'types' field using PostgreSQL ArrayField to store
        # multiple project types.  Uses a CharField as the base type.
        migrations.AddField(
            model_name="project",
            name="types",
            field=django.contrib.postgres.fields.ArrayField(
                base_field=models.CharField(max_length=100),
                default=list,
                size=None,
                blank=True,
            ),
        ),
        # Create the DatabaseEntry model.  This model stores
        # configuration details for external databases associated with a
        # project.  The status field indicates whether the last
        # synchronisation succeeded.
        migrations.CreateModel(
            name="DatabaseEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("db_name", models.CharField(max_length=255)),
                ("token", models.CharField(max_length=255)),
                ("asset_id", models.CharField(max_length=255)),
                ("xlsform", models.CharField(max_length=255)),
                ("status", models.BooleanField(default=False)),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="database_entries",
                        to="core.project",
                    ),
                ),
            ],
            options={
                "unique_together": {("project", "db_name")},
            },
        ),
    ]