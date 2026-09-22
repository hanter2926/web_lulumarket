from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def wallet(request):
	return render(request, "wallet/wallet.html")


@login_required
def transactions(request):
	return render(request, "wallet/transactions.html", {"transactions": []})
