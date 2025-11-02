from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0009_databaseentry_last_manual_update_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='DatabaseEntryEditRequest',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('submission_id', models.CharField(max_length=64)),
                ('requested_at', models.DateTimeField(auto_now=True)),
                ('entry', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='edit_requests', to='core.databaseentry')),
            ],
            options={
                'ordering': ['-requested_at'],
                'unique_together': {('entry', 'submission_id')},
            },
        ),
        migrations.AddIndex(
            model_name='databaseentryeditrequest',
            index=models.Index(fields=['entry', 'requested_at'], name='core_editreq_entry_req_idx'),
        ),
    ]
