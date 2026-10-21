from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0007_email_otp_challenges"),
    ]

    operations = [
        migrations.AddField(
            model_name="customuser",
            name="is_email_verified",
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name="emailotpchallenge",
            name="purpose",
            field=models.CharField(
                choices=[
                    ("signup", "Signup verification"),
                    ("login", "Login"),
                    ("password_reset", "Password reset"),
                ],
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="emailotpthrottle",
            name="purpose",
            field=models.CharField(
                choices=[
                    ("signup", "Signup verification"),
                    ("login", "Login"),
                    ("password_reset", "Password reset"),
                ],
                max_length=20,
            ),
        ),
    ]
