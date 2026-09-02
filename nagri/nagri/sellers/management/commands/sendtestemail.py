from django.core.management.base import BaseCommand, CommandError
from django.core.mail import send_mail
from django.conf import settings


class Command(BaseCommand):
    help = "Send a test email to confirm SMTP configuration works."

    def add_arguments(self, parser):
        parser.add_argument("recipient", nargs="?", default=None)

    def handle(self, *args, **options):
        recipient = options["recipient"] or getattr(settings, "DEFAULT_FROM_EMAIL", None) or "admin@example.com"

        try:
            sent = send_mail(
                subject="NAGRI SMTP test email",
                message="This is a Django SMTP test email from NAGRI.",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient],
                fail_silently=False,
            )
            if sent:
                self.stdout.write(self.style.SUCCESS(f"SMTP test email sent successfully to {recipient}"))
                return
            self.stdout.write(self.style.WARNING(f"SMTP send_mail returned 0 for {recipient}; check server logs."))
        except Exception as exc:
            raise CommandError(f"SMTP test email failed for {recipient}: {type(exc).__name__}: {exc}")
