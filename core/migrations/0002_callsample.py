"""
Migration to add the CallSample model for telephone interview sample assignments.

This migration introduces a new model named ``CallSample`` which stores
sampled respondent phone numbers for each project/quota combination.  Each
sample record references the project and quota cell it belongs to, the
respondent (Person) and their mobile number.  The ``assigned_to`` field
tracks which user has been given the number to call, while ``completed``
and ``completed_at`` store the outcome of that call.  A unique
constraint on ``(project, mobile)`` prevents duplicate sampling of the
same mobile number for a given project.

The migration depends on the initial schema and should be applied
afterwards.  If you are upgrading an existing database you can run
``python manage.py migrate`` to create the new table.
"""

from __future__ import annotations

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = False

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='CallSample',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('assigned_at', models.DateTimeField(blank=True, null=True)),
                ('completed', models.BooleanField(default=False)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('assigned_to', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='assigned_samples', to=settings.AUTH_USER_MODEL)),
                ('mobile', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='core.mobile')),
                ('person', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='core.person')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='call_samples', to='core.project')),
                ('quota', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='call_samples', to='core.quota')),
            ],
            options={
                'unique_together': {('project', 'mobile')},
            },
        ),
    ]