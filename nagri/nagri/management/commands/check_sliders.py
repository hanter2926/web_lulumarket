from django.core.management.base import BaseCommand
from accounts.models import HomeSlider

class Command(BaseCommand):
    help = 'Prints HomeSlider counts and details for debugging'

    def handle(self, *args, **options):
        total = HomeSlider.objects.count()
        active = HomeSlider.objects.filter(is_active=True).count()
        self.stdout.write(f"Total sliders: {total}")
        self.stdout.write(f"Active sliders: {active}\n")

        for s in HomeSlider.objects.all().order_by('display_order'):
            has_image = bool(getattr(s.image, 'name', None))
            self.stdout.write(f"Slider ID={s.pk}")
            self.stdout.write(f"Title={s.title}")
            self.stdout.write(f"Active={s.is_active}")
            self.stdout.write(f"Has image={has_image}")
            self.stdout.write('')
