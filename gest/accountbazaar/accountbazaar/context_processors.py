from notifications.models import Notification


def product_context(request):
    if not request.user.is_authenticated:
        return {"unread_notifications": 0, "is_moderator": False}
    return {
        "unread_notifications": Notification.objects.filter(
            recipient=request.user,
            is_read=False,
        ).count(),
        "is_moderator": request.user.is_staff,
    }
