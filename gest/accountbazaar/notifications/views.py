from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Notification


@login_required
def inbox(request):
	return render(request, "notifications/inbox.html", {
		"notifications": request.user.notifications.all(),
		"unread_count": request.user.notifications.filter(is_read=False).count(),
	})


@login_required
@require_POST
def mark_read(request, notification_id):
	notification = get_object_or_404(Notification, pk=notification_id, recipient=request.user)
	notification.is_read = True
	notification.save(update_fields=("is_read",))
	return redirect(notification.link or "notifications:inbox")
