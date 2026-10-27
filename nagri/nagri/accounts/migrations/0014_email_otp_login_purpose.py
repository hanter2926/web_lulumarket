from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0013_pendingsignup_alter_emailotpchallenge_user"),
    ]

    operations = [
        migrations.AlterField(
            model_name="emailotpchallenge",
            name="purpose",
            field=models.CharField(
                choices=[
                    ("signup", "Signup verification"),
                    ("password_reset", "Password reset"),
                    ("login", "Login"),
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
                    ("password_reset", "Password reset"),
                    ("login", "Login"),
                ],
                max_length=20,
            ),
        ),
    ]
