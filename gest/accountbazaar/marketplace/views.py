from django.contrib.auth.views import redirect_to_login
from django.db.models import Q
from django.shortcuts import redirect, render

from .forms import ListingForm
from .models import Listing


def listings(request):
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
		},
	)
