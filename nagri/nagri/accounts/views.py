from datetime import timedelta

from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from orders.models import Order

from .models import Address, CustomUser, PaymentMethod, UserProfile
from .serializers import AddressSerializer, PaymentMethodSerializer, UserProfileSerializer, UserSerializer
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
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from .models import HomeSlider
from .forms import HomeSliderForm
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
        phone = (request.data.get("phone") or "").strip()
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
    success_url = reverse_lazy('password_reset_done')
    
    def form_valid(self, form):
        # Attempt to send the password reset email and surface failures in logs.
        try:
            # Determine domain/protocol for the reset link. Prefer SITE_URL when configured.
            site_url = getattr(settings, "SITE_URL", None) or None
            domain_override = None
            use_https = False
            if site_url:
                try:
                    parsed = urlparse(site_url)
                    # If SITE_URL included scheme, use its scheme to determine https
                    if parsed.scheme:
                        use_https = parsed.scheme.lower() == "https"
                    # Build domain_override as host[:port]
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
            # Log the real exception for debugging (do NOT log secrets or tokens)
            email = form.cleaned_data.get('email') if hasattr(form, 'cleaned_data') else None
            logger.exception("Failed to send password reset email for recipient=%s", email)
            messages.error(self.request, "Unable to send password reset email right now. Please try again later.")
            return self.form_invalid(form)

        return super().form_valid(form)


class PasswordResetDoneView(auth_views.PasswordResetDoneView):
    template_name = 'registration/password_reset_done.html'


class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    template_name = 'registration/password_reset_confirm.html'
    success_url = reverse_lazy('password_reset_complete')


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


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def request_otp(request):
    payload = getattr(request, "data", request.POST)
    raw_phone = (payload.get("phone") or "").strip()
    phone = normalize_phone_number(raw_phone)

    if not raw_phone:
        return Response({"detail": "Phone number is required."}, status=status.HTTP_400_BAD_REQUEST)
    if not phone:
        return Response({"detail": "Enter a valid phone number."}, status=status.HTTP_400_BAD_REQUEST)

    user = find_user_by_phone(phone)
    if not user:
        return Response({"detail": "No account found with this phone number. Please register first."}, status=status.HTTP_404_NOT_FOUND)

    profile, _ = UserProfile.objects.get_or_create(user=user)
    if profile.last_otp_sent_at and timezone.now() - profile.last_otp_sent_at < timedelta(seconds=OTP_RESEND_COOLDOWN_SECONDS):
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
            return Response({"detail": "Unable to send OTP right now. Please try again later."}, status=500)

    except Exception:
        profile.otp = ""
        profile.otp_expires_at = None
        profile.save(update_fields=["otp", "otp_expires_at", "updated_at"])
        logger.exception("Failed to send registration phone OTP for phone=%s", phone)
        return Response({"detail": "Unable to send OTP right now. Please try again later."}, status=500)

    # Delivery succeeded — record send timestamp
    profile.last_otp_sent_at = timezone.now()
    profile.save(update_fields=["last_otp_sent_at", "updated_at"])

    user.phone = phone
    user.save(update_fields=["phone", "updated_at"])

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
def verify_otp(request):
    payload = getattr(request, "data", request.POST)
    raw_phone = (payload.get("phone") or "").strip()
    phone = normalize_phone_number(raw_phone)
    otp = (payload.get("otp") or "").strip()

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

    auth_login(request, user)
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

        if not email or not password:
            return render(request, "accounts/auth.html", {"active_tab": "login", "error": "Email and password are required."})

        user = CustomUser.objects.filter(email__iexact=email).first()
        if not user or not user.check_password(password):
            return render(request, "accounts/auth.html", {"active_tab": "login", "error": "Invalid email or password."})

        if not getattr(user, "is_active", True):
            return render(request, "accounts/auth.html", {"active_tab": "login", "error": "Your account is inactive. Please contact support."})

        profile = UserProfile.objects.filter(user=user).first()
        if profile is None or not profile.is_phone_verified:
            return render(request, "accounts/auth.html", {"active_tab": "login", "error": "Verify your phone number before logging in."})

        auth_login(request, user)
        # Redirect users by role: owner -> owner dashboard, vendor -> seller dashboard, else customer dashboard
        if getattr(user, "is_owner", False):
            return redirect("sellers:owner_dashboard")
        if getattr(user, "is_vendor", False):
            return redirect("sellers:dashboard")
        return redirect("dashboard_page")

    return render(request, "accounts/auth.html", {"active_tab": "login"})


def logout_view(request):
    auth_logout(request)
    return redirect("home")


def signup_form_view(request):
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip()
        password = request.POST.get("password") or ""
        phone = (request.POST.get("phone") or "").strip()
        full_name = (request.POST.get("full_name") or "").strip()

        if not email or not password or not phone:
            return render(request, "accounts/auth.html", {"active_tab": "signup", "error": "Email, password, and phone number are required."})

        if CustomUser.objects.filter(email__iexact=email).exists():
            return render(request, "accounts/auth.html", {"active_tab": "signup", "error": "An account with this email already exists."})

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
        return render(request, "accounts/otp_login.html", {"phone": phone, "message": "Account created. OTP sent to your phone."})

    return render(request, "accounts/auth.html", {"active_tab": "signup"})


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
    return render(request, "accounts/otp_login.html")


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
