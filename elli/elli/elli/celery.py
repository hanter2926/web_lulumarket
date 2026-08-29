import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'elli.settings')

app = Celery('elli')

# Using a string here means the worker will not have to
# pickle the object when using Windows/older kombu.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
