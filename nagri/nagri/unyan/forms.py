from django import forms


class ContactSupportForm(forms.Form):
    name = forms.CharField(
        max_length=100,
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Your full name"}),
    )
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "you@example.com"}),
    )
    subject = forms.CharField(
        max_length=200,
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "How can we help?"}),
    )
    message = forms.CharField(
        required=True,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 6, "placeholder": "Tell us about your issue or question..."}),
    )
