from django.apps import AppConfig


class ProductsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "products"
    def ready(self):
        # Import signal handlers to ensure they are registered when the app is ready
        try:
            import products.signals  # noqa: F401
        except Exception:
            # Avoid raising during migrations or other manage.py commands if signals import fails
            pass
