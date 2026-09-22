from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render

from .forms import LoginForm, RegisterForm
from .models import Account, AccountMembership


class AccountLoginView(LoginView):
	authentication_form = LoginForm
	template_name = "accounts/login.html"


def register(request):
	if request.user.is_authenticated:
		return redirect("marketplace:listings")

	form = RegisterForm(request.POST or None)
	if request.method == "POST" and form.is_valid():
		user = form.save()
		account = Account.objects.create(owner=user)
		AccountMembership.objects.create(account=account, user=user, role="owner")
		request.session["active_account_id"] = account.id
		login(request, user)
		return redirect("marketplace:listings")
	return render(request, "accounts/register.html", {"form": form})


@login_required
def account_logout(request):
	if request.method == "POST":
		logout(request)
		return redirect("home")
	return redirect("marketplace:listings")


@login_required
def profile(request):
	return render(request, "accounts/profile.html")


@login_required
def switch_account(request, account_id):
	if request.method == "POST" and AccountMembership.objects.filter(
		account_id=account_id,
		user=request.user,
	).exists():
		request.session["active_account_id"] = account_id
	return redirect(request.POST.get("next", "marketplace:listings"))
