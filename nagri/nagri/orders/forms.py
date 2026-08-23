from django import forms
from .models import Order
from accounts.models import Address


class CheckoutAddressForm(forms.ModelForm):
    """Form for entering/selecting shipping address during checkout"""
    
    class Meta:
        model = Address
        fields = [
            'label', 'full_name', 'phone', 
            'address_line_1', 'address_line_2',
            'city', 'state', 'country', 'pincode', 'landmark'
        ]
        widgets = {
            'label': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Home, Office'
            }),
            'full_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Full Name'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '10-digit mobile number',
                'type': 'tel'
            }),
            'address_line_1': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'House No., Building Name'
            }),
            'address_line_2': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Road name, Area, Colony (Optional)'
            }),
            'city': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'City'
            }),
            'state': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'State'
            }),
            'country': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Country',
                'value': 'India'
            }),
            'pincode': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '6-digit pincode'
            }),
            'landmark': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Landmark (Optional)'
            }),
        }
    
    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        if phone and not phone.replace(' ', '').replace('-', '').isdigit():
            raise forms.ValidationError('Phone number must contain only digits.')
        if phone and len(phone.replace(' ', '').replace('-', '')) != 10:
            raise forms.ValidationError('Phone number must be 10 digits.')
        return phone
    
    def clean_pincode(self):
        pincode = self.cleaned_data.get('pincode')
        if pincode and not pincode.isdigit():
            raise forms.ValidationError('Pincode must contain only digits.')
        if pincode and len(pincode) != 6:
            raise forms.ValidationError('Pincode must be 6 digits.')
        return pincode


class DeliveryMethodForm(forms.Form):
    """Form for selecting delivery method"""
    
    DELIVERY_CHOICES = [
        ('standard', 'Standard Delivery (5-7 days) - FREE'),
        ('express', 'Express Delivery (2-3 days) - ₹50'),
        ('overnight', 'Overnight Delivery - ₹100'),
    ]
    
    delivery_method = forms.ChoiceField(
        choices=DELIVERY_CHOICES,
        widget=forms.RadioSelect(attrs={
            'class': 'form-check-input'
        }),
        initial='standard'
    )


class PaymentMethodForm(forms.Form):
    """Form for selecting payment method"""
    
    PAYMENT_CHOICES = [
        ('razorpay', 'Credit/Debit Card (Razorpay)'),
        ('netbanking', 'Net Banking'),
        ('upi', 'UPI'),
        ('wallet', 'Digital Wallet'),
        ('cod', 'Cash on Delivery'),
    ]
    
    payment_method = forms.ChoiceField(
        choices=PAYMENT_CHOICES,
        widget=forms.RadioSelect(attrs={
            'class': 'form-check-input'
        }),
        initial='razorpay'
    )


class CouponForm(forms.Form):
    """Form for applying coupon code"""
    
    coupon_code = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter coupon code',
            'autocomplete': 'off'
        })
    )


class OrderForm(forms.ModelForm):
    """Form for creating order (for admin use)"""
    
    class Meta:
        model = Order
        fields = [
            'user', 'order_number', 'subtotal', 'discount_amount',
            'delivery_charge', 'total_amount', 'status',
            'delivery_method', 'payment_method', 'coupon_code'
        ]
