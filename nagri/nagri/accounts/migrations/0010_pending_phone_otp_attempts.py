from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0009_phone_change_and_account_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="pending_phone_otp_attempts",
            field=models.PositiveSmallIntegerField(default=0),
        ),
    ]
