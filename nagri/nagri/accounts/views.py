from datetime import timedelta

from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes, renderer_classes
from rest_framework.response import Response
from rest_framework.renderers import BrowsableAPIRenderer, JSONRenderer
from rest_framework_simplejwt.tokens import RefreshToken

from orders.models import Order

from .models import Address, CustomUser, PaymentMethod, UserProfile
from .serializers import AddressSerializer, PaymentMethodSerializer, UserProfileSerializer, UserSerializer
from .forms_account_settings import ProfileForm, NotificationForm, AppearanceForm, LanguageForm, AddressForm
from .utils import (
    OTP_RESEND_COOLDOWN_SECONDS,
    OTP_TTL_MINUTES,
    generate_otp,
    get_phone_variants,
    normalize_phone_number,
    send_otp_to_phone,
)
import logging
from django.conf import settings

logger = logging.getLogger(__name__)
from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from .models import HomeSlider
from .forms import HomeSliderForm, SignupForm
from .decorators import owner_required
from .forms import SafePasswordResetForm
from urllib.parse import urlparse


class IsOwnerOrAdmin(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        user = getattr(request, "user", None)
        return bool(user and user.is_authenticated and (user == getattr(obj, "user", None) or user.is_staff or user == obj))


def find_user_by_phone(phone):
    variants = get_phone_variants(phone)
    for variant in variants:
        user = CustomUser.objects.filter(phone__iexact=variant).first()
        if user:
            return user

        profile = UserProfile.objects.filter(phone__iexact=variant).select_related("user").first()
        if profile and profile.user:
            return profile.user

    return None


def get_phone_verification_error_message(user):
    if not getattr(user, "is_active", True):
        return "Your account is inactive. Please contact support."

    profile = UserProfile.objects.filter(user=user).first()
    if profile and not profile.is_phone_verified:
        return "Verify your phone number before logging in."

    return "Verify your phone number before logging in."


class UserViewSet(viewsets.ModelViewSet):
    queryset = CustomUser.objects.all().order_by("id")
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_staff:
            return CustomUser.objects.all().order_by("id")
        return CustomUser.objects.filter(id=self.request.user.id).order_by("id")

    @action(detail=False, methods=["get"], permission_classes=[permissions.IsAuthenticated])
    def me(self, request):
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

    @action(detail=False, methods=["post"], permission_classes=[permissions.AllowAny])
    def register(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        user.is_active = False
        user.save(update_fields=["is_active", "updated_at"])

        profile, _ = UserProfile.objects.get_or_create(user=user)
        raw_phone = (request.data.get("phone") or "").strip()
        phone = normalize_phone_number(raw_phone)
        if raw_phone and not phone:
            return Response({"detail": "Enter a valid phone number."}, status=400)
        if phone:
            profile.full_name = request.data.get("full_name") or user.get_full_name() or user.email
            profile.phone = phone
            profile.is_phone_verified = False

            otp_code = generate_otp()

            # Persist OTP record before attempting delivery
            profile.otp = otp_code
            profile.otp_expires_at = timezone.now() + timedelta(minutes=OTP_TTL_MINUTES)
            profile.save(update_fields=["full_name", "phone", "is_phone_verified", "otp", "otp_expires_at", "updated_at"])
            user.phone = phone
            user.save(update_fields=["phone", "updated_at"])

            try:
                send_result = send_otp_to_phone(phone, otp_code)
                status_sent = False
                if isinstance(send_result, dict):
                    status_sent = str(send_result.get("status") or "").lower() == "sent"
                else:
                    status_sent = True

                if not status_sent:
                    # Delivery failed — invalidate saved OTP
                    profile.otp = ""
                    profile.otp_expires_at = None
                    profile.save(update_fields=["otp", "otp_expires_at", "updated_at"])
                    logger.warning("Register API OTP provider returned non-sent status for phone=%s provider_result=%s", phone, send_result)
                    return Response({"detail": "Unable to send OTP right now. Please try again later."}, status=500)

            except Exception:
                # Delivery exception — invalidate saved OTP and log
                profile.otp = ""
                profile.otp_expires_at = None
                profile.save(update_fields=["otp", "otp_expires_at", "updated_at"])
                logger.exception("Failed to send registration phone OTP for phone=%s", phone)
                return Response({"detail": "Unable to send OTP right now. Please try again later."}, status=500)

            # Delivery succeeded — record send timestamp
            profile.last_otp_sent_at = timezone.now()
            profile.save(update_fields=["last_otp_sent_at", "updated_at"])

        return Response({
            "detail": "User registered successfully. Verify your phone OTP to complete setup.",
            "user": self.get_serializer(user).data,
            "otp_sent": bool(phone),
            "phone": phone,
        }, status=201)

    @action(detail=False, methods=["post"], permission_classes=[permissions.AllowAny])
    def login(self, request):
        email = request.data.get("email")
        password = request.data.get("password")
        if not email or not password:
            return Response({"detail": "Email and password are required."}, status=status.HTTP_400_BAD_REQUEST)

        user = CustomUser.objects.filter(email__iexact=email).first()
        if not user or not user.check_password(password):
            return Response({"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)

        if not getattr(user, "is_active", True):
            return Response({"detail": "Your account is inactive. Please contact support."}, status=status.HTTP_403_FORBIDDEN)

        profile = UserProfile.objects.filter(user=user).first()
        if profile is None or not profile.is_phone_verified:
            return Response({"detail": "Verify your phone number before logging in."}, status=status.HTTP_403_FORBIDDEN)

        auth_login(request, user)
        refresh = RefreshToken.for_user(user)
        return Response({
            "user": self.get_serializer(user).data,
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        })

    @action(detail=False, methods=["post"], permission_classes=[permissions.AllowAny])
    def phone_login(self, request):
        raw_phone = (request.data.get("phone") or "").strip()
        phone = normalize_phone_number(raw_phone)
        otp = (request.data.get("otp") or "").strip()

        if not raw_phone:
            return Response({"detail": "Phone number is required."}, status=status.HTTP_400_BAD_REQUEST)
        if not phone:
            return Response({"detail": "Enter a valid phone number."}, status=status.HTTP_400_BAD_REQUEST)
        if not otp:
            return Response({"detail": "Phone number and OTP are required."}, status=status.HTTP_400_BAD_REQUEST)

        user = find_user_by_phone(phone)
        if not user:
            return Response({"detail": "No account found with this phone number. Please register first."}, status=status.HTTP_404_NOT_FOUND)

        profile = UserProfile.objects.filter(user=user).first()
        if not profile or not profile.otp or profile.otp != otp:
            return Response({"detail": "Invalid OTP."}, status=status.HTTP_400_BAD_REQUEST)

        if profile.otp_expires_at and timezone.now() > profile.otp_expires_at:
            return Response({"detail": "OTP has expired. Please request a new one."}, status=status.HTTP_400_BAD_REQUEST)

        if not getattr(user, "is_active", True):
            user.is_active = True
            user.save(update_fields=["is_active", "updated_at"])

        profile.is_phone_verified = True
        profile.otp = ""
        profile.otp_expires_at = None
        profile.save(update_fields=["is_phone_verified", "otp", "otp_expires_at", "updated_at"])

        user.phone = phone
        user.save(update_fields=["phone", "updated_at"])

        auth_login(request, user)
        refresh = RefreshToken.for_user(user)
        return Response({
            "user": self.get_serializer(user).data,
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        })

    @action(detail=False, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def logout(self, request):
        auth_logout(request)
        return Response({"detail": "Logged out successfully."}, status=status.HTTP_200_OK)


# Simple view wrappers to use Django's built-in auth views with project templates
class PasswordResetView(auth_views.PasswordResetView):
    template_name = 'registration/password_reset_form.html'
    email_template_name = 'registration/password_reset_email.html'
    subject_template_name = 'registration/password_reset_subject.txt'
    form_class = SafePasswordResetForm
    success_url = reverse_lazy('accounts:password_reset_done')
    
    def form_valid(self, form):
        # Django's PasswordResetView.form_valid() already calls form.save() once.
        # We only need to preserve the project-specific SITE_URL override and
        # surface SMTP/send failures without triggering a second email send.
        try:
            site_url = getattr(settings, "SITE_URL", None) or None
            domain_override = None
            use_https = False
            if site_url:
                try:
                    parsed = urlparse(site_url)
                    if parsed.scheme:
                        use_https = parsed.scheme.lower() == "https"
                    domain_override = parsed.netloc or parsed.path
                except Exception:
                    domain_override = None

            form.save(
                subject_template_name=self.subject_template_name,
                email_template_name=self.email_template_name,
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
                request=self.request,
                domain_override=domain_override,
                use_https=use_https,
            )
        except Exception:
            email = form.cleaned_data.get('email') if hasattr(form, 'cleaned_data') else None
            logger.exception("Failed to send password reset email for recipient=%s", email)
            messages.error(self.request, "Unable to send password reset email right now. Please try again later.")
            return self.form_invalid(form)

        return redirect(self.get_success_url())


class PasswordResetDoneView(auth_views.PasswordResetDoneView):
    template_name = 'registration/password_reset_done.html'


class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    template_name = 'registration/password_reset_confirm.html'
    success_url = reverse_lazy('accounts:password_reset_complete')


class PasswordResetCompleteView(auth_views.PasswordResetCompleteView):
    template_name = 'registration/password_reset_complete.html'


class UserProfileViewSet(viewsets.ModelViewSet):
    queryset = UserProfile.objects.select_related("user").all().order_by("id")
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]

    def get_queryset(self):
        if self.request.user.is_staff:
            return UserProfile.objects.select_related("user").all().order_by("id")
        return UserProfile.objects.filter(user=self.request.user).order_by("id")

    @action(detail=False, methods=["patch"], permission_classes=[permissions.IsAuthenticated])
    def update_profile(self, request):
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        serializer = self.get_serializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

@login_required
def account_settings(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    addresses = Address.objects.filter(user=request.user).order_by('-is_default', '-created_at')

    if request.method == 'POST':
        # handle profile update separately
        if 'profile_submit' in request.POST:
            pform = ProfileForm(request.POST, request.FILES, instance=profile)
            if pform.is_valid():
                pform.save()
                messages.success(request, 'Profile updated.')
                return redirect('account_settings')
        elif 'notif_submit' in request.POST:
            nform = NotificationForm(request.POST, instance=profile)
            if nform.is_valid():
                nform.save()
                messages.success(request, 'Notification settings updated.')
                return redirect('account_settings')
        elif 'appearance_submit' in request.POST:
            aform = AppearanceForm(request.POST, instance=profile)
            if aform.is_valid():
                aform.save()
                messages.success(request, 'Appearance preference saved.')
                return redirect('account_settings')
        elif 'address_submit' in request.POST:
            addr_form = AddressForm(request.POST)
            if addr_form.is_valid():
                addr = addr_form.save(commit=False)
                addr.user = request.user
                addr.save()
                if addr.is_default:
                    Address.objects.filter(user=request.user).exclude(id=addr.id).update(is_default=False)
                messages.success(request, 'Address added.')
                return redirect('account_settings')
    else:
        pform = ProfileForm(instance=profile)
        nform = NotificationForm(instance=profile)
        aform = AppearanceForm(initial={'appearance': profile.appearance})
        addr_form = AddressForm()

    # Create address/form pairs for template rendering (allows per-address inline edit forms)
    address_pairs = [(addr, AddressForm(instance=addr)) for addr in addresses]

    context = {
        'profile': profile,
        'pform': pform,
        'nform': nform,
        'aform': aform,
        'addr_form': addr_form,
        'addresses': addresses,
        'address_pairs': address_pairs,
    }

    return render(request, 'accounts/settings.html', context)


@login_required
def edit_address(request, pk):
    addr = get_object_or_404(Address, pk=pk)
    if addr.user != request.user and not request.user.is_staff:
        messages.error(request, 'You do not have permission to edit this address.')
        return redirect('account_settings')

    if request.method == 'POST':
        form = AddressForm(request.POST, instance=addr)
        if form.is_valid():
            address = form.save()
            if address.is_default:
                Address.objects.filter(user=request.user).exclude(id=address.id).update(is_default=False)
            messages.success(request, 'Address updated.')
        else:
            messages.error(request, 'Please correct the errors in the form.')

    return redirect('account_settings')


@login_required
def delete_address(request, pk):
    if request.method != 'POST':
        return redirect('account_settings')

    addr = get_object_or_404(Address, pk=pk)
    if addr.user != request.user and not request.user.is_staff:
        messages.error(request, 'You do not have permission to delete this address.')
        return redirect('account_settings')

    was_default = addr.is_default
    addr.delete()
    messages.success(request, 'Address deleted.')

    # If deleted address was default, make another address default if exists
    if was_default:
        other = Address.objects.filter(user=request.user).order_by('-created_at').first()
        if other:
            other.is_default = True
            other.save(update_fields=['is_default', 'updated_at'])

    return redirect('account_settings')


@login_required
def set_default_address(request, pk):
    if request.method != 'POST':
        return redirect('account_settings')

    addr = get_object_or_404(Address, pk=pk)
    if addr.user != request.user and not request.user.is_staff:
        messages.error(request, 'You do not have permission to update this address.')
        return redirect('account_settings')

    Address.objects.filter(user=request.user).exclude(id=addr.id).update(is_default=False)
    addr.is_default = True
    addr.save(update_fields=['is_default', 'updated_at'])
    messages.success(request, 'Default address updated.')
    return redirect('account_settings')


class AddressViewSet(viewsets.ModelViewSet):
    serializer_class = AddressSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_staff:
            return Address.objects.select_related("user").all().order_by("-is_default", "-created_at")
        return Address.objects.filter(user=self.request.user).order_by("-is_default", "-created_at")

    def perform_create(self, serializer):
        address = serializer.save(user=self.request.user)
        if address.is_default:
            Address.objects.filter(user=self.request.user).exclude(id=address.id).update(is_default=False)


class PaymentMethodViewSet(viewsets.ModelViewSet):
    serializer_class = PaymentMethodSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_staff:
            return PaymentMethod.objects.select_related("user").all().order_by("-is_default", "-created_at")
        return PaymentMethod.objects.filter(user=self.request.user).order_by("-is_default", "-created_at")

    def perform_create(self, serializer):
        method = serializer.save(user=self.request.user)
        if method.is_default:
            PaymentMethod.objects.filter(user=self.request.user).exclude(id=method.id).update(is_default=False)


def _is_browser_form_request(request):
    accept = request.META.get("HTTP_ACCEPT", "")
    return request.content_type in {"application/x-www-form-urlencoded", "multipart/form-data"} and (
        "text/html" in accept or not accept
    )


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
@renderer_classes([JSONRenderer, BrowsableAPIRenderer])
def request_otp(request):
    browser_request = _is_browser_form_request(request)
    payload = getattr(request, "data", request.POST)
    raw_phone = (payload.get("phone") or "").strip()
    phone = normalize_phone_number(raw_phone)

    if not raw_phone:
        if browser_request:
            return render(request, "accounts/otp_login.html", {"error": "Phone number is required."}, status=400)
        return Response({"detail": "Phone number is required."}, status=status.HTTP_400_BAD_REQUEST)
    if not phone:
        if browser_request:
            return render(request, "accounts/otp_login.html", {"phone": raw_phone, "error": "Enter a valid phone number."}, status=400)
        return Response({"detail": "Enter a valid phone number."}, status=status.HTTP_400_BAD_REQUEST)

    user = find_user_by_phone(phone)
    if not user:
        if browser_request:
            return render(request, "accounts/otp_login.html", {"phone": phone, "error": "No account found with this phone number. Please register first."}, status=404)
        return Response({"detail": "No account found with this phone number. Please register first."}, status=status.HTTP_404_NOT_FOUND)

    profile, _ = UserProfile.objects.get_or_create(user=user)
    if profile.last_otp_sent_at and timezone.now() - profile.last_otp_sent_at < timedelta(seconds=OTP_RESEND_COOLDOWN_SECONDS):
        if browser_request:
            remaining = OTP_RESEND_COOLDOWN_SECONDS - int((timezone.now() - profile.last_otp_sent_at).total_seconds())
            return render(request, "accounts/otp_login.html", {"phone": phone, "otp_sent": True, "error": f"Please wait {max(1, remaining)} seconds before requesting another OTP.", "resend_available_in": max(1, remaining)}, status=429)
        return Response({"detail": f"Please wait {OTP_RESEND_COOLDOWN_SECONDS} seconds before requesting another OTP."}, status=status.HTTP_429_TOO_MANY_REQUESTS)

    profile.phone = phone
    profile.is_phone_verified = False

    # Generate OTP and persist before attempting delivery
    otp_code = generate_otp()
    profile.otp = otp_code
    profile.otp_expires_at = timezone.now() + timedelta(minutes=OTP_TTL_MINUTES)
    profile.save(update_fields=["phone", "is_phone_verified", "otp", "otp_expires_at", "updated_at"])

    try:
        send_result = send_otp_to_phone(phone, otp_code)
        status_sent = False
        if isinstance(send_result, dict):
            status_sent = str(send_result.get("status") or "").lower() == "sent"
        else:
            status_sent = True

        if not status_sent:
            # Invalidate saved OTP
            profile.otp = ""
            profile.otp_expires_at = None
            profile.save(update_fields=["otp", "otp_expires_at", "updated_at"])
            logger.warning("OTP provider returned non-sent status for phone=%s provider_result=%s", phone, send_result)
            if browser_request:
                return render(request, "accounts/otp_login.html", {"phone": phone, "otp_sent": False, "error": "Unable to send OTP right now. Please try again later."}, status=500)
            return Response({"detail": "Unable to send OTP right now. Please try again later."}, status=500)

    except Exception:
        profile.otp = ""
        profile.otp_expires_at = None
        profile.save(update_fields=["otp", "otp_expires_at", "updated_at"])
        logger.exception("Failed to send registration phone OTP for phone=%s", phone)
        if browser_request:
            return render(request, "accounts/otp_login.html", {"phone": phone, "otp_sent": False, "error": "Unable to send OTP right now. Please try again later."}, status=500)
        return Response({"detail": "Unable to send OTP right now. Please try again later."}, status=500)

    # Delivery succeeded — record send timestamp
    profile.last_otp_sent_at = timezone.now()
    profile.save(update_fields=["last_otp_sent_at", "updated_at"])

    user.phone = phone
    user.save(update_fields=["phone", "updated_at"])

    if browser_request:
        request.session["otp_phone"] = phone
        return redirect("accounts:otp_login_page")
    return Response({"detail": "OTP sent successfully.", "phone": phone})


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def signup_submit(request):
    payload = getattr(request, "data", request.POST)
    email = (payload.get("email") or "").strip()
    password = payload.get("password") or ""
    raw_phone = (payload.get("phone") or "").strip()
    full_name = (payload.get("full_name") or "").strip()
    phone = normalize_phone_number(raw_phone)

    if not email or not password or not raw_phone:
        return Response({"detail": "Email, password, and phone number are required."}, status=status.HTTP_400_BAD_REQUEST)
    if not phone:
        return Response({"detail": "Enter a valid phone number."}, status=status.HTTP_400_BAD_REQUEST)

    if CustomUser.objects.filter(email__iexact=email).exists():
        return Response({"detail": "An account with this email already exists."}, status=status.HTTP_400_BAD_REQUEST)
    if find_user_by_phone(phone):
        return Response({"detail": "An account with this phone number already exists."}, status=status.HTTP_400_BAD_REQUEST)

    user = CustomUser.objects.create_user(
        email=email,
        username=email,
        password=password,
        phone=phone,
        first_name=(full_name.split()[0] if full_name else ""),
        last_name=" ".join(full_name.split()[1:]) if full_name else "",
        is_active=False,
    )

    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.full_name = full_name or user.get_full_name() or email
    profile.phone = phone
    profile.is_phone_verified = False

    # Generate OTP and persist before attempting delivery
    otp_code = generate_otp()
    profile.otp = otp_code
    profile.otp_expires_at = timezone.now() + timedelta(minutes=OTP_TTL_MINUTES)
    profile.save(update_fields=["full_name", "phone", "is_phone_verified", "otp", "otp_expires_at", "updated_at"])

    try:
        send_result = send_otp_to_phone(phone, otp_code)
        status_sent = False
        if isinstance(send_result, dict):
            status_sent = str(send_result.get("status") or "").lower() == "sent"
        else:
            status_sent = True

        if not status_sent:
            profile.otp = ""
            profile.otp_expires_at = None
            profile.save(update_fields=["otp", "otp_expires_at", "updated_at"])
            logger.warning("Signup OTP provider returned non-sent status for phone=%s provider_result=%s", phone, send_result)
            return Response({"detail": "Unable to send OTP right now. Please try again later."}, status=500)

    except Exception:
        profile.otp = ""
        profile.otp_expires_at = None
        profile.save(update_fields=["otp", "otp_expires_at", "updated_at"])
        logger.exception("Failed to send signup phone OTP for phone=%s", phone)
        return Response({"detail": "Unable to send OTP right now. Please try again later."}, status=500)

    profile.last_otp_sent_at = timezone.now()
    profile.save(update_fields=["last_otp_sent_at", "updated_at"])

    return Response({
        "detail": "Account created successfully. OTP sent to your phone.",
        "user": UserSerializer(user).data,
        "phone": phone,
    }, status=201)


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
@renderer_classes([JSONRenderer, BrowsableAPIRenderer])
def verify_otp(request):
    browser_request = _is_browser_form_request(request)
    payload = getattr(request, "data", request.POST)
    raw_phone = (payload.get("phone") or "").strip()
    if browser_request and not raw_phone:
        raw_phone = (request.session.get("otp_phone") or "").strip()
    phone = normalize_phone_number(raw_phone)
    otp = (payload.get("otp") or "").strip()

    if not raw_phone:
        if browser_request:
            return render(request, "accounts/otp_login.html", {"error": "Phone number is required."}, status=400)
        return Response({"detail": "Phone number is required."}, status=status.HTTP_400_BAD_REQUEST)
    if not phone:
        if browser_request:
            return render(request, "accounts/otp_login.html", {"phone": raw_phone, "error": "Enter a valid phone number."}, status=400)
        return Response({"detail": "Enter a valid phone number."}, status=status.HTTP_400_BAD_REQUEST)
    if not otp:
        if browser_request:
            return render(request, "accounts/otp_login.html", {"phone": phone, "error": "Enter the 6-digit OTP sent to your phone."}, status=400)
        return Response({"detail": "Phone number and OTP are required."}, status=status.HTTP_400_BAD_REQUEST)

    user = find_user_by_phone(phone)
    if not user:
        if browser_request:
            return render(request, "accounts/otp_login.html", {"phone": phone, "error": "No account found with this phone number. Please register first."}, status=404)
        return Response({"detail": "No account found with this phone number. Please register first."}, status=status.HTTP_404_NOT_FOUND)

    profile = UserProfile.objects.filter(user=user).first()
    if not profile or not profile.otp or profile.otp != otp:
        if browser_request:
            return render(request, "accounts/otp_login.html", {"phone": phone, "otp_sent": True, "error": "That OTP is incorrect. Please check the code and try again."}, status=400)
        return Response({"detail": "Invalid OTP."}, status=status.HTTP_400_BAD_REQUEST)

    if profile.otp_expires_at and timezone.now() > profile.otp_expires_at:
        if browser_request:
            return render(request, "accounts/otp_login.html", {"phone": phone, "otp_sent": True, "error": "This OTP has expired. Please request a new one."}, status=400)
        return Response({"detail": "OTP has expired. Please request a new one."}, status=status.HTTP_400_BAD_REQUEST)

    if not getattr(user, "is_active", True):
        user.is_active = True
        user.save(update_fields=["is_active", "updated_at"])

    profile.is_phone_verified = True
    profile.otp = ""
    profile.otp_expires_at = None
    profile.save(update_fields=["is_phone_verified", "otp", "otp_expires_at", "updated_at"])

    auth_login(request, user)
    if browser_request:
        request.session.pop("otp_phone", None)
        return redirect("accounts:dashboard_page")
    refresh = RefreshToken.for_user(user)
    return Response({
        "detail": "Phone number verified successfully.",
        "user": UserSerializer(user).data,
        "refresh": str(refresh),
        "access": str(refresh.access_token),
    })


def email_login_view(request):
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip()
        password = request.POST.get("password") or ""
        next_url = request.POST.get("next") or request.GET.get("next") or ""

        if not email or not password:
            return render(request, "accounts/auth.html", {"active_tab": "login", "error": "Email and password are required.", "next": next_url})

        user = CustomUser.objects.filter(email__iexact=email).first()
        if not user:
            return render(request, "accounts/auth.html", {"active_tab": "login", "error": "Invalid email or password.", "next": next_url})

        if not getattr(user, "is_active", True):
            return render(request, "accounts/auth.html", {"active_tab": "login", "error": "Your account is inactive. Please contact support.", "next": next_url})

        authenticated_user = authenticate(request, username=user.email, password=password)
        if authenticated_user is None:
            return render(request, "accounts/auth.html", {"active_tab": "login", "error": "Invalid email or password.", "next": next_url})

        profile = UserProfile.objects.filter(user=user).first()
        if profile is None or not profile.is_phone_verified:
            return render(request, "accounts/auth.html", {"active_tab": "login", "error": "Verify your phone number before logging in.", "next": next_url})

        auth_login(request, authenticated_user)
        if request.POST.get("remember"):
            request.session.set_expiry(settings.SESSION_COOKIE_AGE)
        else:
            request.session.set_expiry(0)

        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)

        # Redirect users by role: owner -> owner dashboard, vendor -> seller dashboard, else customer dashboard
        if getattr(authenticated_user, "is_owner", False):
            return redirect("sellers:owner_dashboard")
        if getattr(authenticated_user, "is_vendor", False):
            return redirect("sellers:dashboard")
        return redirect("accounts:dashboard_page")

    return render(request, "accounts/auth.html", {"active_tab": "login", "next": request.GET.get("next", "")})


def logout_view(request):
    auth_logout(request)
    return redirect("home")


def signup_form_view(request):
    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        password = form.cleaned_data["password"]
        phone = form.cleaned_data["phone"]
        full_name = form.cleaned_data["full_name"].strip()

        user = CustomUser.objects.create_user(
            email=email,
            username=email,
            password=password,
            phone=phone,
            first_name=(full_name.split()[0] if full_name else ""),
            last_name=" ".join(full_name.split()[1:]) if full_name else "",
            is_active=False,
        )

        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.full_name = full_name or user.get_full_name() or email
        profile.phone = phone
        profile.is_phone_verified = False

        otp_code = generate_otp()

        # Persist OTP before attempting delivery
        profile.otp = otp_code
        profile.otp_expires_at = timezone.now() + timedelta(minutes=5)
        profile.save(update_fields=["full_name", "phone", "is_phone_verified", "otp", "otp_expires_at", "updated_at"])

        try:
            send_result = send_otp_to_phone(phone, otp_code)
            status_sent = False
            if isinstance(send_result, dict):
                status_sent = str(send_result.get("status") or "").lower() == "sent"
            else:
                status_sent = True

            if not status_sent:
                profile.otp = ""
                profile.otp_expires_at = None
                profile.save(update_fields=["otp", "otp_expires_at", "updated_at"])
                logger.warning("Signup form OTP provider returned non-sent status for phone=%s provider_result=%s", phone, send_result)
                messages.error(request, "Unable to send verification OTP. Please try again later.")
                return render(request, "accounts/auth.html", {"active_tab": "signup", "error": "Unable to send verification OTP. Please try again later."})

        except Exception:
            profile.otp = ""
            profile.otp_expires_at = None
            profile.save(update_fields=["otp", "otp_expires_at", "updated_at"])
            logger.exception("Failed to send signup form phone OTP for phone=%s", phone)
            messages.error(request, "Unable to send verification OTP. Please try again later.")
            return render(request, "accounts/auth.html", {"active_tab": "signup", "error": "Unable to send verification OTP. Please try again later."})

        profile.last_otp_sent_at = timezone.now()
        profile.save(update_fields=["last_otp_sent_at", "updated_at"])
        request.session["otp_phone"] = phone
        return render(request, "accounts/otp_login.html", {"phone": phone, "otp_sent": True, "message": "Account created. OTP sent to your phone.", "resend_available_in": OTP_RESEND_COOLDOWN_SECONDS})

    return render(request, "accounts/auth.html", {"active_tab": "signup", "form": form})


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def dashboard(request):
    profile = UserProfile.objects.filter(user=request.user).first()
    addresses = Address.objects.filter(user=request.user)
    payment_methods = PaymentMethod.objects.filter(user=request.user)
    orders = Order.objects.filter(user=request.user).order_by("-created_at")[:10]
    wishlist_count = 0
    cart_count = 0
    return Response({
        "profile": UserProfileSerializer(profile).data if profile else None,
        "addresses": AddressSerializer(addresses, many=True).data,
        "payment_methods": PaymentMethodSerializer(payment_methods, many=True).data,
        "orders": Order.objects.filter(user=request.user).order_by("-created_at").values("id", "order_number", "status", "tracking_status", "total_amount"),
        "addresses_count": addresses.count(),
        "payment_methods_count": payment_methods.count(),
        "wishlist_count": wishlist_count,
        "cart_count": cart_count,
    })


def login_page(request):
    return render(request, "accounts/auth.html", {"active_tab": "login"})


def signup_page(request):
    return render(request, "accounts/auth.html", {"active_tab": "signup"})


def otp_login_page(request):
    phone = request.session.get("otp_phone", "")
    profile = None
    if phone:
        user = find_user_by_phone(phone)
        profile = UserProfile.objects.filter(user=user).first() if user else None

    resend_available_in = 0
    if profile and profile.last_otp_sent_at:
        elapsed = int((timezone.now() - profile.last_otp_sent_at).total_seconds())
        resend_available_in = max(0, OTP_RESEND_COOLDOWN_SECONDS - elapsed)

    return render(request, "accounts/otp_login.html", {
        "phone": phone,
        "otp_sent": bool(phone),
        "resend_available_in": resend_available_in,
    })


@login_required(login_url="/accounts/auth/")
def dashboard_page(request):
    profile = UserProfile.objects.filter(user=request.user).first()
    addresses = Address.objects.filter(user=request.user).order_by("-is_default", "-created_at")
    payment_methods = PaymentMethod.objects.filter(user=request.user).order_by("-is_default", "-created_at")
    orders = Order.objects.filter(user=request.user).order_by("-created_at")[:10]
    return render(request, "accounts/dashboard.html", {
        "profile": profile,
        "addresses": addresses,
        "payment_methods": payment_methods,
        "orders": orders,
        "wishlist_count": 0,
        "cart_count": 0,
    })


@owner_required
def owner_sliders_list(request):
    sliders = HomeSlider.objects.all().order_by('display_order', '-created_at')
    return render(request, 'accounts/owner/sliders_list.html', {'sliders': sliders})


@owner_required
def owner_sliders_add(request):
    if request.method == 'POST':
        form = HomeSliderForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Slider added')
            return redirect('owner_sliders_list')
    else:
        form = HomeSliderForm()
    return render(request, 'accounts/owner/slider_form.html', {'form': form, 'is_edit': False})


@owner_required
def owner_sliders_edit(request, pk):
    slider = get_object_or_404(HomeSlider, pk=pk)
    if request.method == 'POST':
        form = HomeSliderForm(request.POST, request.FILES, instance=slider)
        if form.is_valid():
            form.save()
            messages.success(request, 'Slider updated')
            return redirect('owner_sliders_list')
    else:
        form = HomeSliderForm(instance=slider)
    return render(request, 'accounts/owner/slider_form.html', {'form': form, 'is_edit': True, 'slider': slider})


@owner_required
def owner_sliders_delete(request, pk):
    slider = get_object_or_404(HomeSlider, pk=pk)
    if request.method == 'POST':
        slider.delete()
        messages.success(request, 'Slider deleted')
        return redirect('owner_sliders_list')
    return render(request, 'accounts/owner/slider_confirm_delete.html', {'slider': slider})


@owner_required
def owner_sliders_toggle(request, pk):
    slider = get_object_or_404(HomeSlider, pk=pk)
    slider.is_active = not slider.is_active
    slider.save()
    return redirect('owner_sliders_list')
