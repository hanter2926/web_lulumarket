import os

from django.core.management.base import BaseCommand
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

        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "username": username,
                "is_staff": True,
                "is_superuser": True,
                "is_active": True,
            },
        )

        user.username = username
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
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