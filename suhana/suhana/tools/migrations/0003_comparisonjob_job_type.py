from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tools", "0002_comparisonqueuecontrol_comparisonjob"),
    ]

    operations = [
        migrations.AddField(
            model_name="comparisonjob",
            name="job_type",
            field=models.CharField(
                choices=[("compare", "Comparison"), ("compress", "Compression")],
                default="compare",
                max_length=12,
            ),
        ),
    ]
