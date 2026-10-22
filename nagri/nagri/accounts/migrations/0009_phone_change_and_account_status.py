from django.db import migrations, models


def mark_existing_inactive_users_disabled(apps, schema_editor):
    CustomUser = apps.get_model("accounts", "CustomUser")
    CustomUser.objects.filter(is_active=False).update(account_status="admin_disabled")


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0008_email_verification"),
    ]

    operations = [
        migrations.AddField(
            model_name="customuser",
            name="account_status",
            field=models.CharField(
                choices=[
                    ("pending_verification", "Pending verification"),
                    ("active", "Active"),
                    ("admin_disabled", "Disabled by administrator"),
                ],
                default="active",
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="pending_phone",
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="pending_phone_otp",
            field=models.CharField(blank=True, max_length=6, null=True),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="pending_phone_otp_expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(
            mark_existing_inactive_users_disabled,
            migrations.RunPython.noop,
        ),
    ]
