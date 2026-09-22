from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import render

from accounts.models import FraudSignal
from ads.models import AdCampaign
from marketplace.models import Listing
from notifications.models import Notification
from payments.models import Order


@login_required
def owner_dashboard(request):
    campaigns = AdCampaign.objects.filter(owner=request.user)
    impressions = campaigns.aggregate(total=Sum("impressions"))["total"] or 0
    clicks = campaigns.aggregate(total=Sum("clicks"))["total"] or 0
    return render(request, "owner_dashboard.html", {
        "listing_count": Listing.objects.filter(seller=request.user).count(),
        "order_count": Order.objects.filter(buyer=request.user).count(),
        "sales_count": Order.objects.filter(seller=request.user).count(),
        "campaign_count": campaigns.count(),
        "impressions": impressions,
        "clicks": clicks,
        "ctr": round(clicks / impressions * 100, 2) if impressions else 0,
        "unread_notifications": Notification.objects.filter(recipient=request.user, is_read=False).count(),
        "open_fraud_signals": FraudSignal.objects.filter(user=request.user, is_resolved=False).count(),
        "campaigns": campaigns.select_related("placement").order_by("-created_at")[:10],
    })
