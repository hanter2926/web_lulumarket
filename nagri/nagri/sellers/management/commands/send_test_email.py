from django.core.management.base import BaseCommand, CommandError
from django.core.mail import send_mail
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Send a test email to confirm SMTP configuration works."

    def add_arguments(self, parser):
        parser.add_argument("recipient", nargs="?", default=None)

    def handle(self, *args, **options):
        recipient = options["recipient"] or getattr(settings, "DEFAULT_FROM_EMAIL", None) or "admin@example.com"

        try:
            sent = send_mail(
                "NAGRI Email Test",
                "This is a test email from the NAGRI Django application.",
                settings.DEFAULT_FROM_EMAIL,
                [recipient],
                fail_silently=False,
            )
            if sent:
                self.stdout.write(self.style.SUCCESS(f"SMTP test email sent successfully to {recipient}"))
                return
            self.stdout.write(self.style.WARNING(f"SMTP send_mail returned 0 for {recipient}; check server logs."))
        except Exception:
            # Log details to application logs (render/dev) but raise a generic error to console
            logger.exception("Failed to send test email for recipient=%s", recipient)
            raise CommandError("SMTP test email failed; check application logs for details")
