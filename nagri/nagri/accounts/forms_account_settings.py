from django import forms
from .models import UserProfile, Address


class ProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['full_name', 'phone', 'avatar']


class NotificationForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['notif_order_updates', 'notif_promotions', 'notif_important']


class AppearanceForm(forms.ModelForm):
    APPEARANCE_CHOICES = [
        ('light', 'Light'),
        ('dark', 'Dark'),
        ('system', 'System Default'),
    ]

    appearance = forms.ChoiceField(choices=APPEARANCE_CHOICES)

    class Meta:
        model = UserProfile
        fields = ['appearance']


class LanguageForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['language']


class AddressForm(forms.ModelForm):
    class Meta:
        model = Address
        fields = ['label', 'full_name', 'phone', 'address_line_1', 'address_line_2', 'city', 'state', 'country', 'pincode', 'landmark', 'is_default']
