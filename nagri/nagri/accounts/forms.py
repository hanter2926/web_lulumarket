from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .models import CustomUser


class SignupForm(forms.Form):
    full_name = forms.CharField(max_length=150, required=True)
    email = forms.EmailField(required=True)
    phone = forms.CharField(max_length=20, required=True)
    password = forms.CharField(widget=forms.PasswordInput, required=True)
    confirm_password = forms.CharField(widget=forms.PasswordInput, required=True)
    terms = forms.BooleanField(required=True)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if CustomUser.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "This email is already registered. Please login or use Forgot Password."
            )
        return email

    def clean_phone(self):
        from .utils import normalize_phone_number

        phone = normalize_phone_number(self.cleaned_data["phone"])
        if not phone:
            raise forms.ValidationError("Enter a valid phone number.")
        if CustomUser.objects.filter(phone__iexact=phone).exists():
            raise forms.ValidationError("An account with this phone number already exists.")
        return phone

    def clean_password(self):
        password = self.cleaned_data["password"]
        candidate = CustomUser(
            email=self.data.get("email", "").strip().lower(),
            username=self.data.get("email", "").strip().lower(),
        )
        try:
            validate_password(password, candidate)
        except ValidationError as exc:
            raise forms.ValidationError(exc.messages)
        return password

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirmation = cleaned_data.get("confirm_password")
        if password and confirmation and password != confirmation:
            self.add_error("confirm_password", "The two password fields didn't match.")
        return cleaned_data


from .models import HomeSlider


class HomeSliderForm(forms.ModelForm):
    class Meta:
        model = HomeSlider
        fields = [
            'title', 'subtitle', 'image', 'mobile_image', 'button_text', 'button_link', 'display_order', 'is_active'
        ]
        widgets = {
            'button_link': forms.TextInput(attrs={'placeholder': 'https://example.com/path or /products/?id=1'}),
        }

    def clean_button_link(self):
        link = self.cleaned_data.get('button_link', '').strip()
        # Basic safety: disallow javascript: urls
        if link.lower().startswith('javascript:'):
            raise forms.ValidationError('Invalid URL')
        return link


from django.contrib.auth.forms import PasswordResetForm as DjangoPasswordResetForm
from django.template import loader
from django.core.mail import EmailMultiAlternatives
import logging

_logger = logging.getLogger(__name__)


class SafePasswordResetForm(DjangoPasswordResetForm):
    """PasswordResetForm that surfaces delivery failures instead of
    swallowing them. This ensures callers (views/management commands)
    can detect SMTP problems.
    """

    def send_mail(
        self,
        subject_template_name,
        email_template_name,
        context,
        from_email,
        to_email,
        html_email_template_name=None,
    ):
        """Send email and raise if sending failed (0 sent) or an exception occurs.

        We intentionally do not swallow exceptions here so higher layers
        can log them and show generic errors to users.
        """
        subject = loader.render_to_string(subject_template_name, context)
        subject = "".join(subject.splitlines())
        body = loader.render_to_string(email_template_name, context)

        email_message = EmailMultiAlternatives(subject, body, from_email, [to_email])
        if html_email_template_name is not None:
            html_email = loader.render_to_string(html_email_template_name, context)
            email_message.attach_alternative(html_email, "text/html")

        # Let exceptions propagate so callers can handle/log them.
        sent_count = email_message.send()
        if not sent_count:
            # No message sent — surface as an error
            _logger.warning("Password reset send_mail returned 0 for recipient=%s", to_email)
            raise Exception("No emails were sent by the configured email backend")

