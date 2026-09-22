from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def create_dispute(request):
	return render(request, "disputes/create_dispute.html")
