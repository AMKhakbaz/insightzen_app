from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0018_membership_edit_data_membership_product_matrix_ai_and_more'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='ReviewTask',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('task_size', models.PositiveIntegerField(default=0)),
                ('reviewed_count', models.PositiveIntegerField(default=0)),
                ('measure_definition', models.JSONField(blank=True, default=list)),
                ('columns', models.JSONField(blank=True, default=list)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('assigned_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='assigned_review_tasks', to='auth.user')),
                ('entry', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='review_tasks', to='core.databaseentry')),
                ('reviewer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='review_tasks', to='auth.user')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='ReviewRow',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('submission_id', models.CharField(max_length=64)),
                ('data', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('task', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='rows', to='core.reviewtask')),
            ],
            options={
                'ordering': ['created_at'],
                'unique_together': {('task', 'submission_id')},
            },
        ),
        migrations.CreateModel(
            name='ReviewAction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(choices=[('assigned', 'Assigned'), ('started', 'Started'), ('submitted', 'Submitted'), ('updated_checklist', 'Updated Checklist')], max_length=32)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('row', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='actions', to='core.reviewrow')),
            ],
            options={
                'ordering': ['timestamp'],
            },
        ),
        migrations.CreateModel(
            name='ChecklistResponse',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('measure_id', models.CharField(max_length=128)),
                ('label', models.CharField(max_length=255)),
                ('value', models.BooleanField(default=False)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('row', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='checklist_responses', to='core.reviewrow')),
            ],
            options={
                'unique_together': {('row', 'measure_id')},
            },
        ),
    ]
