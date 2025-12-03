from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0019_review_models'),
    ]

    operations = [
        migrations.AddField(
            model_name='reviewrow',
            name='review_started_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='reviewrow',
            name='review_submitted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
