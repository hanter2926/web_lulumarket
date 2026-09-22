from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from payments.models import Order
from payments.services import open_dispute
from notifications.services import record_audit

from .forms import DisputeForm, ReportForm
from .models import Dispute, Report


@login_required
def create_dispute(request, order_id=None):
	if order_id is None:
		return render(request, "disputes/forbidden.html", status=400)
	order = get_object_or_404(Order, pk=order_id)
	if request.user.id not in (order.buyer_id, order.seller_id):
		return render(request, "disputes/forbidden.html", status=403)
	if hasattr(order, "dispute"):
		return redirect("disputes:detail", dispute_id=order.dispute.id)
	form = DisputeForm(request.POST or None, request.FILES or None)
	if request.method == "POST" and form.is_valid():
		try:
			dispute = open_dispute(
				order=order,
				opened_by=request.user,
				reason=form.cleaned_data["reason"],
				description=form.cleaned_data.get("description", ""),
				evidence=form.cleaned_data.get("evidence"),
			)
		except ValueError:
			return render(request, "disputes/forbidden.html", status=400)
		record_audit(actor=request.user, action="DISPUTE_OPENED", obj=dispute, metadata={"order_id": order.order_id})
		return redirect("disputes:detail", dispute_id=dispute.id)
	return render(request, "disputes/create_dispute.html", {"form": form, "order": order})


@login_required
def detail(request, dispute_id):
	dispute = get_object_or_404(Dispute.objects.select_related("order", "opened_by"), pk=dispute_id)
	if request.user.id not in (dispute.order.buyer_id, dispute.order.seller_id) and not request.user.is_staff:
		return render(request, "disputes/forbidden.html", status=403)
	return render(request, "disputes/dispute_detail.html", {"dispute": dispute})


@login_required
@require_http_methods(["GET", "POST"])
def create_report(request, target_type, target_id):
	if target_type not in {"listing", "user", "order"}:
		return render(request, "disputes/forbidden.html", status=404)
	form = ReportForm(request.POST or None, request.FILES or None)
	if request.method == "POST" and form.is_valid():
		report = form.save(commit=False)
		report.reporter = request.user
		report.target_type = target_type
		report.target_id = target_id
		report.save()
		record_audit(actor=request.user, action="REPORT_CREATED", obj=report, metadata={"target_type": target_type, "target_id": target_id})
		return redirect("notifications:inbox")
	return render(request, "disputes/report.html", {"form": form, "target_type": target_type, "target_id": target_id})


@login_required
def moderation(request):
	if not request.user.is_staff:
		return render(request, "disputes/forbidden.html", status=403)
	return render(request, "disputes/moderation.html", {
		"reports": Report.objects.select_related("reporter", "moderator").order_by("-created_at")[:50],
		"disputes": Dispute.objects.select_related("order", "opened_by").order_by("-created_at")[:50],
	})
