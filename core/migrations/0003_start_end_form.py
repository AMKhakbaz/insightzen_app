from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_callsample'),
    ]

    operations = [
        migrations.AddField(
            model_name='interview',
            name='start_form',
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='interview',
            name='end_form',
            field=models.DateTimeField(null=True, blank=True),
        ),
    ]