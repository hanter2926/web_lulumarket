from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import ListingForm
from .models import Listing


@login_required
def listings(request):
	if request.method == "POST":
		form = ListingForm(request.POST)
		if form.is_valid():
			listing = form.save(commit=False)
			listing.seller = request.user
			listing.save()
			return redirect("marketplace:listings")
	else:
		form = ListingForm()

	return render(
		request,
		"marketplace/listings.html",
		{
			"form": form,
			"listings": Listing.objects.select_related("seller").order_by("-created_at"),
		},
	)
