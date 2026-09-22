from django.contrib.auth.views import redirect_to_login
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import Account, AccountMembership

from .forms import ListingForm
from .models import Listing


def listings(request):
	active_account = None
	accounts = Account.objects.none()
	if request.user.is_authenticated:
		accounts = Account.objects.filter(memberships__user=request.user).distinct()
		if not accounts.exists():
			active_account = Account.objects.create(owner=request.user)
			AccountMembership.objects.create(account=active_account, user=request.user, role="owner")
			accounts = Account.objects.filter(memberships__user=request.user).distinct()
		else:
			active_account = accounts.filter(pk=request.session.get("active_account_id")).first()
			if active_account is None:
				active_account = accounts.first()
			request.session["active_account_id"] = active_account.id

	if request.method == "POST":
		if not request.user.is_authenticated:
			return redirect_to_login(request.get_full_path())
		form = ListingForm(request.POST)
		if form.is_valid():
			listing = form.save(commit=False)
			listing.seller = request.user
			listing.save()
			return redirect("marketplace:listings")
	else:
		form = ListingForm()

	query = request.GET.get("q", "").strip()
	category = request.GET.get("category", "").strip()
	listing_query = Listing.objects.select_related("seller").order_by("-created_at")
	if query:
		listing_query = listing_query.filter(
			Q(title__icontains=query) | Q(description__icontains=query)
		)
	if category:
		listing_query = listing_query.filter(category=category)

	return render(
		request,
		"marketplace/listings.html",
		{
			"form": form,
			"listings": listing_query,
			"query": query,
			"selected_category": category,
			"categories": Listing.CATEGORY_CHOICES,
			"active_account": active_account,
			"accounts": accounts,
		},
	)


def sell_account(request):
	form = ListingForm(request.POST or None)
	if request.method == "POST" and request.user.is_authenticated and form.is_valid():
		listing = form.save(commit=False)
		listing.seller = request.user
		listing.save()
		return redirect("marketplace:listings")
	return render(request, "marketplace/sell_account.html", {"form": form})


def listing_detail(request, listing_id):
	listing = get_object_or_404(Listing.objects.select_related("seller"), pk=listing_id)
	return render(request, "marketplace/listing_detail.html", {"listing": listing})
