from .celery import app as celery_app

# Expose Celery app as a module-level variable named ``celery_app``.
__all__ = ('celery_app',)

