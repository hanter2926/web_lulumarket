from django import forms

from .models import Dispute, Report


class DisputeForm(forms.ModelForm):
    class Meta:
        model = Dispute
        fields = ("reason", "description", "evidence")
        widgets = {
            "reason": forms.Select(choices=(
                ("PAYMENT", "Payment issue"),
                ("NOT_RECEIVED", "Item not received"),
                ("NOT_AS_DESCRIBED", "Item not as described"),
                ("HANDOFF", "Handoff problem"),
                ("SELLER", "Seller issue"),
                ("BUYER", "Buyer issue"),
                ("SUSPICIOUS", "Suspicious activity"),
                ("OTHER", "Other"),
            )),
            "description": forms.Textarea(attrs={"rows": 5, "placeholder": "Describe the problem without including passwords or private credentials."}),
        }

    def clean_evidence(self):
        evidence = self.cleaned_data.get("evidence")
        if evidence and evidence.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Evidence must be smaller than 5 MB.")
        return evidence


class ReportForm(forms.ModelForm):
    class Meta:
        model = Report
        fields = ("reason", "description", "evidence")
        widgets = {
            "reason": forms.Select(choices=(
                ("SUSPICIOUS_LISTING", "Suspicious listing"),
                ("MISLEADING", "Misleading information"),
                ("FRAUD_ATTEMPT", "Fraud attempt"),
                ("PAYMENT", "Payment issue"),
                ("ABUSE", "Abusive behavior"),
                ("FAKE_IDENTITY", "Fake identity"),
                ("UNAUTHORIZED", "Unauthorized content"),
                ("OTHER", "Other"),
            )),
            "description": forms.Textarea(attrs={"rows": 5, "placeholder": "Share facts for moderator review."}),
        }

    def clean_evidence(self):
        evidence = self.cleaned_data.get("evidence")
        if evidence and evidence.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Evidence must be smaller than 5 MB.")
        return evidence