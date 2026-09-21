from django.contrib.auth.decorators import user_passes_test
from django.db.models import Count
from django.shortcuts import render
from django.utils import timezone

from accounts.models import LoginHistory, SellerVerification, User, UserKYC
from ads.models import AdPlacement
from marketplace.models import Listing
from tournaments.models import Tournament


@user_passes_test(lambda user: user.is_active and user.is_staff)
def admin_dashboard(request):
    now = timezone.now()
    locked_users = User.objects.filter(account_locked_until__gt=now).count()

    context = {
        "user_metrics": [
            ("Total Users", User.objects.count(), "users"),
            ("Verified Users", User.objects.filter(is_email_verified=True).count(), "verified"),
            ("Sellers", User.objects.filter(is_seller=True).count(), "sellers"),
            ("Suspended Users", User.objects.filter(is_active=False).count(), "suspended"),
        ],
        "marketplace_metrics": [
            ("Listings", Listing.objects.count()),
            ("Pending Verification", Listing.objects.filter(is_verified=False).count()),
            ("Sold", Listing.objects.filter(status__iexact="sold").count()),
            ("Reports", "--"),
            ("Disputes", "--"),
        ],
        "tournament_metrics": [
            ("Free", Tournament.objects.filter(entry_type="free").count()),
            ("Paid / Restricted", Tournament.objects.filter(entry_type="paid").count()),
            ("Upcoming", Tournament.objects.filter(start_time__gt=now).count()),
            ("Live", Tournament.objects.filter(status__iexact="live").count()),
            ("Completed", Tournament.objects.filter(status__iexact="completed").count()),
        ],
        "payment_metrics": [(label, "--") for label in ("Pending", "Successful", "Refunds", "Reconciliation")],
        "ad_metrics": [
            ("Placements", AdPlacement.objects.count()),
            ("Active Ads", AdPlacement.objects.filter(is_active=True).count()),
            ("Revenue Reports", "--"),
        ],
        "security_metrics": [
            ("Login Attempts", LoginHistory.objects.count()),
            ("Suspicious Activity", LoginHistory.objects.filter(is_suspicious=True).count()),
            ("Audit Logs", "--"),
        ],
        "attention_items": [
            ("Pending KYC reviews", UserKYC.objects.filter(status=UserKYC.Status.PENDING).count()),
            ("Pending seller reviews", SellerVerification.objects.filter(status=SellerVerification.Status.PENDING).count()),
            ("Locked accounts", locked_users),
            ("Failed logins", LoginHistory.objects.filter(status=LoginHistory.Status.FAILED).count()),
        ],
        "recent_listings": Listing.objects.select_related("seller").order_by("-created_at")[:5],
        "recent_logins": LoginHistory.objects.select_related("user").order_by("-timestamp")[:5],
        "listing_categories": Listing.objects.values("category").annotate(total=Count("id")).order_by("category"),
    }
    return render(request, "admin_dashboard.html", context)
