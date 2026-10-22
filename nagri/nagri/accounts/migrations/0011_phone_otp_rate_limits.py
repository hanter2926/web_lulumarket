from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0010_pending_phone_otp_attempts"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="otp_attempts",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="otp_request_count",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="otp_request_window_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
