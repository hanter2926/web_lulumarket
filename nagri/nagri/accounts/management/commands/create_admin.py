import os

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = "Create or update admin user"

    def handle(self, *args, **options):
        User = get_user_model()

        email = os.environ.get("ADMIN_EMAIL")
        password = os.environ.get("ADMIN_PASSWORD")
        username = os.environ.get("ADMIN_USERNAME", "admin")

        if not email or not password:
            self.stdout.write(
                self.style.ERROR(
                    "ADMIN_EMAIL or ADMIN_PASSWORD is not set."
                )
            )
            return

        user = User.objects.filter(email__iexact=email).first()
        if (
            user
            and (
                user.account_status == User.AccountStatus.ADMIN_DISABLED
                or not user.is_active
            )
        ):
            raise CommandError(
                "The configured admin account is disabled. Reactivate it explicitly in Django admin before running this command."
            )

        created = user is None
        if created:
            user = User(
                email=email,
                username=username,
                is_staff=True,
                is_superuser=True,
                is_active=True,
                account_status=User.AccountStatus.ACTIVE,
            )

        user.username = username
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.account_status = User.AccountStatus.ACTIVE
        user.set_password(password)
        user.save()

        if created:
            self.stdout.write(
                self.style.SUCCESS(f"Admin created: {email}")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Admin updated: {email}")
            )