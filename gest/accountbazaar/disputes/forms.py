from django import forms
from pathlib import Path

from .models import Dispute, Report


class DisputeForm(forms.ModelForm):
    ALLOWED_EVIDENCE_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
    ALLOWED_EVIDENCE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}
    MAX_EVIDENCE_SIZE = 5 * 1024 * 1024
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
        if evidence and evidence.size > self.MAX_EVIDENCE_SIZE:
            raise forms.ValidationError("Evidence must be smaller than 5 MB.")
        if evidence and (evidence.content_type not in self.ALLOWED_EVIDENCE_TYPES or Path(evidence.name).suffix.lower() not in self.ALLOWED_EVIDENCE_EXTENSIONS):
            raise forms.ValidationError("Evidence must be a JPG, PNG, WebP, or PDF file.")
        return evidence


class ReportForm(forms.ModelForm):
    ALLOWED_EVIDENCE_TYPES = DisputeForm.ALLOWED_EVIDENCE_TYPES
    ALLOWED_EVIDENCE_EXTENSIONS = DisputeForm.ALLOWED_EVIDENCE_EXTENSIONS
    MAX_EVIDENCE_SIZE = DisputeForm.MAX_EVIDENCE_SIZE
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
        if evidence and evidence.size > self.MAX_EVIDENCE_SIZE:
            raise forms.ValidationError("Evidence must be smaller than 5 MB.")
        if evidence and (evidence.content_type not in self.ALLOWED_EVIDENCE_TYPES or Path(evidence.name).suffix.lower() not in self.ALLOWED_EVIDENCE_EXTENSIONS):
            raise forms.ValidationError("Evidence must be a JPG, PNG, WebP, or PDF file.")
        return evidence