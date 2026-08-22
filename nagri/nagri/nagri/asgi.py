import os

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.core.asgi import get_asgi_application
from django.urls import path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nagri.settings")

# Import websocket app routes here when you add consumers.
# Example: from chat.consumers import ChatConsumer

application = ProtocolTypeRouter(
    {
        "http": get_asgi_application(),
        "websocket": AuthMiddlewareStack(
            URLRouter([
                # path("ws/chat/", ChatConsumer.as_asgi()),
            ])
        ),
    }
)
