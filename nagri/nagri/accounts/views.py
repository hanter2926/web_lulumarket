from datetime import timedelta
import secrets

from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.hashers import make_password
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from nagri import views as site_views
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes, renderer_classes
from rest_framework.response import Response
from rest_framework.renderers import BrowsableAPIRenderer, JSONRenderer
from rest_framework_simplejwt.tokens import RefreshToken
from django.http import JsonResponse
from nagri.email_config import send_message
from orders.models import Order

from .models import (
    Address,
    CustomUser,
    EmailOTPChallenge,
    PaymentMethod,
    PendingSignup,
    UserProfile,
)
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
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from .models import HomeSlider
from .decorators import owner_required
from .forms import (
    EmailOTPRequestForm,
    EmailOTPVerifyForm,
    HomeSliderForm,
    SafePasswordResetForm,
    SignupForm,
)
from .email_delivery import classify_email_delivery_error
from .email_otp import (
    EmailOTPStatus,
    request_email_otp,
    verify_email_otp,
)
from urllib.parse import urlparse

PHONE_CHANGE_OTP_MAX_ATTEMPTS = 5
PHONE_OTP_MAX_ATTEMPTS = 5
PHONE_OTP_MAX_REQUESTS_PER_HOUR = 5


class IsOwnerOrAdmin(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        user = getattr(request, "user", None)
        return bool(user and user.is_authenticated and (user == getattr(obj, "user", None) or user.is_staff or user == obj))

#-----  Email Sending------------------
def send_test_email(request):
    success = send_message(
        to_email="vikrampal505@yahoo.com",
        subject="Test Email",
        message="Hello! This email was sent using Brevo."
    )

    if success:
        return JsonResponse({"success": True, "message": "Email sent successfully."})

    return JsonResponse(
        {"success": False, "message": "Email sending failed."},
        status=500
    )
# END------------------------------

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
    if (
        user.account_status != CustomUser.AccountStatus.ACTIVE
        or not getattr(user, "is_active", True)
    ):
        return "Your account is inactive. Please contact support."

    profile = UserProfile.objects.filter(user=user).first()
    if profile and not profile.is_phone_verified:
        return "Verify your phone number before logging in."

    return "Verify your phone number before logging in."


def _consume_phone_otp(user_id, otp, allow_pending_signup=True):
    with transaction.atomic():
        user = CustomUser.objects.select_for_update().get(pk=user_id)
        profile = UserProfile.objects.select_for_update().filter(user=user).first()

        if user.account_status == CustomUser.AccountStatus.ADMIN_DISABLED:
            return user, None, "inactive"
        if user.account_status == CustomUser.AccountStatus.PENDING_VERIFICATION:
            if user.is_active or not allow_pending_signup:
                return user, None, "inactive"
        elif (
            user.account_status != CustomUser.AccountStatus.ACTIVE
            or not user.is_active
        ):
            return user, None, "inactive"

        if not profile:
            return user, None, "invalid"
        if profile.otp_attempts >= PHONE_OTP_MAX_ATTEMPTS:
            return user, profile, "locked"
        if not profile.otp:
            return user, None, "invalid"
        if not profile.otp_expires_at or timezone.now() >= profile.otp_expires_at:
            return user, None, "expired"
        if not secrets.compare_digest(profile.otp, otp):
            profile.otp_attempts += 1
            update_fields = ["otp_attempts", "updated_at"]
            if profile.otp_attempts >= PHONE_OTP_MAX_ATTEMPTS:
                profile.otp = ""
                update_fields.append("otp")
            profile.save(update_fields=update_fields)
            if profile.otp_attempts >= PHONE_OTP_MAX_ATTEMPTS:
                return user, profile, "locked"
            return user, profile, "invalid"

        if user.account_status == CustomUser.AccountStatus.PENDING_VERIFICATION:
            user.account_status = CustomUser.AccountStatus.ACTIVE
            user.is_active = True
            user.save(update_fields=["account_status", "is_active", "updated_at"])

        profile.is_phone_verified = True
        profile.otp = ""
        profile.otp_expires_at = None
        profile.otp_attempts = 0
        profile.save(
            update_fields=[
                "is_phone_verified",
                "otp",
                "otp_expires_at",
                "otp_attempts",
                "updated_at",
            ]
        )

    return user, profile, None


def _issue_phone_otp(profile_id, phone):
    now = timezone.now()
    with transaction.atomic():
        profile = UserProfile.objects.select_for_update().get(pk=profile_id)
        if profile.last_otp_sent_at:
            elapsed = (now - profile.last_otp_sent_at).total_seconds()
            if elapsed < OTP_RESEND_COOLDOWN_SECONDS:
                remaining = max(1, OTP_RESEND_COOLDOWN_SECONDS - int(elapsed))
                return (
                    status.HTTP_429_TOO_MANY_REQUESTS,
                    f"Please wait {remaining} seconds before requesting another OTP.",
                )

        window_start = profile.otp_request_window_started_at
        if not window_start or now - window_start >= timedelta(hours=1):
            profile.otp_request_window_started_at = now
            profile.otp_request_count = 0
        if profile.otp_request_count >= PHONE_OTP_MAX_REQUESTS_PER_HOUR:
            return (
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Hourly OTP request limit reached. Try again later.",
            )

        otp_code = generate_otp()
        profile.phone = phone
        profile.otp = otp_code
        profile.otp_expires_at = now + timedelta(minutes=OTP_TTL_MINUTES)
        profile.otp_attempts = 0
        profile.otp_request_count += 1
        profile.last_otp_sent_at = now
        profile.save(
            update_fields=[
                "phone",
                "otp",
                "otp_expires_at",
                "otp_attempts",
                "otp_request_count",
                "otp_request_window_started_at",
                "last_otp_sent_at",
                "updated_at",
            ]
        )

    try:
        send_result = send_otp_to_phone(phone, otp_code)
        if isinstance(send_result, dict) and str(send_result.get("status") or "").lower() != "sent":
            raise RuntimeError("Phone OTP provider did not confirm delivery")
    except Exception as exc:
        UserProfile.objects.filter(pk=profile_id, otp=otp_code).update(
            otp="",
            otp_expires_at=None,
        )
        logger.error("Phone OTP delivery failed: error_type=%s", type(exc).__name__)
        return (
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Unable to send OTP right now. Please try again later.",
        )

    return status.HTTP_200_OK, "OTP sent to your phone."


def _start_phone_change(user, raw_phone):
    if (
        user.account_status != CustomUser.AccountStatus.ACTIVE
        or not user.is_active
    ):
        return status.HTTP_403_FORBIDDEN, "Your account is inactive. Please contact support."

    phone = normalize_phone_number(str(raw_phone or "").strip())
    if not phone:
        return status.HTTP_400_BAD_REQUEST, "Enter a valid phone number."

    profile, _ = UserProfile.objects.get_or_create(user=user)
    current_phone = normalize_phone_number(profile.phone or user.phone or "")
    if phone == current_phone:
        return status.HTTP_400_BAD_REQUEST, "This phone number is already on your account."

    existing_user = find_user_by_phone(phone)
    if existing_user and existing_user.pk != user.pk:
        return status.HTTP_400_BAD_REQUEST, "An account with this phone number already exists."
    if UserProfile.objects.filter(pending_phone__iexact=phone).exclude(user=user).exists():
        return status.HTTP_400_BAD_REQUEST, "This phone number is already pending verification."

    now = timezone.now()
    if profile.last_otp_sent_at and now - profile.last_otp_sent_at < timedelta(seconds=OTP_RESEND_COOLDOWN_SECONDS):
        return status.HTTP_429_TOO_MANY_REQUESTS, "Please wait before requesting another OTP."

    otp_code = generate_otp()
    profile.pending_phone = phone
    profile.pending_phone_otp = otp_code
    profile.pending_phone_otp_expires_at = now + timedelta(minutes=OTP_TTL_MINUTES)
    profile.pending_phone_otp_attempts = 0
    profile.save(
        update_fields=[
            "pending_phone",
            "pending_phone_otp",
            "pending_phone_otp_expires_at",
            "pending_phone_otp_attempts",
            "updated_at",
        ]
    )

    try:
        send_result = send_otp_to_phone(phone, otp_code)
        status_sent = (
            str(send_result.get("status") or "").lower() == "sent"
            if isinstance(send_result, dict)
            else True
        )
        if not status_sent:
            raise RuntimeError("Phone OTP provider did not confirm delivery")
    except Exception as exc:
        profile.pending_phone = None
        profile.pending_phone_otp = None
        profile.pending_phone_otp_expires_at = None
        profile.pending_phone_otp_attempts = 0
        profile.save(
            update_fields=[
                "pending_phone",
                "pending_phone_otp",
                "pending_phone_otp_expires_at",
                "pending_phone_otp_attempts",
                "updated_at",
            ]
        )
        logger.error("Phone change OTP delivery failed: error_type=%s", type(exc).__name__)
        return status.HTTP_500_INTERNAL_SERVER_ERROR, "Unable to send OTP right now. Please try again later."

    profile.last_otp_sent_at = timezone.now()
    profile.save(update_fields=["last_otp_sent_at", "updated_at"])
    return status.HTTP_200_OK, "OTP sent to the new phone number."


def _consume_phone_change_otp(user_id, otp):
    with transaction.atomic():
        user = CustomUser.objects.select_for_update().get(pk=user_id)
        profile = UserProfile.objects.select_for_update().filter(user=user).first()

        if (
            user.account_status != CustomUser.AccountStatus.ACTIVE
            or not user.is_active
        ):
            return user, None, "inactive"
        if not profile or not profile.pending_phone:
            return user, None, "missing"
        if (
            not profile.pending_phone_otp_expires_at
            or timezone.now() >= profile.pending_phone_otp_expires_at
        ):
            return user, None, "expired"
        if (
            profile.pending_phone_otp_attempts
            >= PHONE_CHANGE_OTP_MAX_ATTEMPTS
        ):
            return user, None, "locked"
        if not profile.pending_phone_otp or not secrets.compare_digest(profile.pending_phone_otp, otp):
            profile.pending_phone_otp_attempts += 1
            update_fields = ["pending_phone_otp_attempts", "updated_at"]
            if (
                profile.pending_phone_otp_attempts
                >= PHONE_CHANGE_OTP_MAX_ATTEMPTS
            ):
                profile.pending_phone_otp = None
                update_fields.append("pending_phone_otp")
            profile.save(update_fields=update_fields)
            return user, None, "locked" if profile.pending_phone_otp_attempts >= PHONE_CHANGE_OTP_MAX_ATTEMPTS else "invalid"

        new_phone = profile.pending_phone
        existing_user = find_user_by_phone(new_phone)
        if existing_user and existing_user.pk != user.pk:
            return user, None, "taken"

        profile.phone = new_phone
        profile.pending_phone = None
        profile.pending_phone_otp = None
        profile.pending_phone_otp_expires_at = None
        profile.pending_phone_otp_attempts = 0
        profile.is_phone_verified = True
        profile.save(
            update_fields=[
                "phone",
                "pending_phone",
                "pending_phone_otp",
                "pending_phone_otp_expires_at",
                "pending_phone_otp_attempts",
                "is_phone_verified",
                "updated_at",
            ]
        )
        user.phone = new_phone
        user.save(update_fields=["phone", "updated_at"])

    return user, profile, None


def _validate_signup_password(password, email, username):
    try:
        validate_password(
            password,
            CustomUser(email=email, username=username),
        )
    except ValidationError as exc:
        return exc.messages
    return []


def _stage_pending_signup(email, username, password, phone, full_name):
    email = email.strip().lower()
    username = username.strip()
    phone = normalize_phone_number(phone)
    phone_variants = get_phone_variants(phone)

    if PendingSignup.objects.filter(email__iexact=email).exists():
        return "pending_exists"
    if CustomUser.objects.filter(email__iexact=email).exists():
        return "email_taken"
    if CustomUser.objects.filter(username__iexact=username).exists():
        return "username_taken"
    if find_user_by_phone(phone):
        return "phone_taken"
    if PendingSignup.objects.filter(phone__in=phone_variants).exists():
        return "phone_taken"
    if PendingSignup.objects.filter(username__iexact=username).exists():
        return "username_taken"

    name_parts = full_name.split()
    try:
        with transaction.atomic():
            PendingSignup.objects.create(
                email=email,
                username=username,
                password_hash=make_password(password),
                phone=phone,
                first_name=name_parts[0] if name_parts else "",
                last_name=" ".join(name_parts[1:]) if name_parts else "",
                full_name=full_name,
            )
    except IntegrityError:
        return "pending_exists"
    return None


def _request_signup_email_otp(email):
    try:
        return request_email_otp(
            email,
            EmailOTPChallenge.Purpose.SIGNUP,
        )
    except Exception as exc:
        _log_email_delivery_failure(exc)
        return "delivery_failed"


def _signup_email_otp_error_response(result):
    if result == "delivery_failed":
        return Response(
            {
                "detail": "Unable to send the verification email right now. Please try again later.",
                "resend_endpoint": reverse("accounts:signup_email_otp_resend"),
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )
    if result == "throttled":
        return Response(
            {
                "detail": "Please wait before requesting another verification code.",
                "resend_endpoint": reverse("accounts:signup_email_otp_resend"),
            },
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )
    return None


class UserViewSet(viewsets.ModelViewSet):
    queryset = CustomUser.objects.all().order_by("id")
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self):
        if self.action == "create":
            return [permissions.AllowAny()]
        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        return self.register(request)

    def get_queryset(self):
        if self.request.user.is_staff:
            return CustomUser.objects.all().order_by("id")
        return CustomUser.objects.filter(id=self.request.user.id).order_by("id")

    @action(detail=False, methods=["get"], permission_classes=[permissions.IsAuthenticated])
    def me(self, request):
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

    @action(detail=False, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def phone_change_request(self, request):
        response_status, detail = _start_phone_change(
            request.user, request.data.get("phone", "")
        )
        return Response({"detail": detail}, status=response_status)

    @action(detail=False, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def phone_change_verify(self, request):
        otp = (request.data.get("otp") or "").strip()
        if not otp:
            return Response(
                {"detail": "Phone number and OTP are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user, profile, otp_error = _consume_phone_change_otp(
            request.user.pk, otp
        )
        if otp_error == "inactive":
            return Response(
                {"detail": "Your account is inactive. Please contact support."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if otp_error == "missing":
            return Response(
                {"detail": "No phone number is awaiting verification."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if otp_error == "expired":
            return Response(
                {"detail": "OTP has expired. Please request a new one."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if otp_error == "locked":
            return Response(
                {"detail": "Too many incorrect codes. Request a new verification code."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        if otp_error == "taken":
            return Response(
                {"detail": "This phone number is already associated with another account."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if otp_error == "invalid":
            return Response(
                {"detail": "Invalid OTP."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {"detail": "Phone number verified successfully.", "user": self.get_serializer(user).data}
        )

    @action(detail=False, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def phone_change_resend(self, request):
        profile = UserProfile.objects.filter(user=request.user).first()
        if not profile or not profile.pending_phone:
            return Response(
                {"detail": "No phone number is awaiting verification."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        response_status, detail = _start_phone_change(
            request.user, profile.pending_phone
        )
        return Response({"detail": detail}, status=response_status)

    @action(detail=False, methods=["post"], permission_classes=[permissions.AllowAny])
    def register(self, request):
        raw_phone = (request.data.get("phone") or "").strip()
        phone = normalize_phone_number(raw_phone)
        if not phone:
            return Response(
                {"detail": "A valid phone number is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        password = serializer.validated_data.get("password")
        if not password:
            return Response(
                {"password": ["This field is required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        password_errors = _validate_signup_password(
            password,
            serializer.validated_data["email"],
            serializer.validated_data["username"],
        )
        if password_errors:
            return Response(
                {"password": password_errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        email = serializer.validated_data["email"]
        username = serializer.validated_data["username"]
        full_name = (request.data.get("full_name") or "").strip()
        stage_error = _stage_pending_signup(
            email,
            username,
            password,
            phone,
            full_name,
        )
        if stage_error:
            detail = {
                "email_taken": "An account with this email already exists.",
                "phone_taken": "An account with this phone number already exists.",
                "username_taken": "An account with this username already exists.",
                "pending_exists": "A signup is already awaiting email verification. Request a new code or verify the existing code.",
            }.get(stage_error, "Unable to start signup. Please try again.")
            return Response(
                {
                    "detail": detail,
                    "resend_endpoint": reverse("accounts:signup_email_otp_resend"),
                },
                status=(
                    status.HTTP_409_CONFLICT
                    if stage_error == "pending_exists"
                    else status.HTTP_400_BAD_REQUEST
                ),
            )

        email_otp_result = _request_signup_email_otp(email)
        email_otp_error = _signup_email_otp_error_response(email_otp_result)
        if email_otp_error:
            return email_otp_error

        return Response({
            "detail": "Signup received. Verify your email to create your account.",
            "email": email,
            "email_otp_sent": True,
            "email_verification_required": True,
            "verify_endpoint": reverse("accounts:signup_email_otp_verify"),
            "resend_endpoint": reverse("accounts:signup_email_otp_resend"),
            "phone": phone,
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], permission_classes=[permissions.AllowAny])
    def login(self, request):
        email = request.data.get("email")
        password = request.data.get("password")
        if not email or not password:
            return Response({"detail": "Email and password are required."}, status=status.HTTP_400_BAD_REQUEST)

        user = CustomUser.objects.filter(email__iexact=email).first()
        if not user or not user.check_password(password):
            return Response({"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)

        if (
            user.account_status != CustomUser.AccountStatus.ACTIVE
            or not user.is_active
        ):
            return Response({"detail": "Your account is inactive. Please contact support."}, status=status.HTTP_403_FORBIDDEN)

        if not user.is_email_verified:
            return Response(
                {"detail": "Verify your email before logging in."},
                status=status.HTTP_403_FORBIDDEN,
            )

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

        user, profile, otp_error = _consume_phone_otp(
            user.pk, otp, allow_pending_signup=False
        )
        if otp_error == "inactive":
            return Response({"detail": "Your account is inactive. Please contact support."}, status=status.HTTP_403_FORBIDDEN)
        if otp_error == "locked":
            return Response({"detail": "Too many incorrect codes. Request a new OTP."}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        if otp_error == "invalid":
            return Response({"detail": "Invalid OTP."}, status=status.HTTP_400_BAD_REQUEST)
        if otp_error == "expired":
            return Response({"detail": "OTP has expired. Please request a new one."}, status=status.HTTP_400_BAD_REQUEST)

        user.phone = phone
        user.save(update_fields=["phone", "updated_at"])

        if not user.is_email_verified:
            return Response(
                {"detail": "Phone verified. Verify your email before logging in."},
                status=status.HTTP_403_FORBIDDEN,
            )

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
            use_https = use_https or not settings.DEBUG

            form.save(
                subject_template_name=self.subject_template_name,
                email_template_name=self.email_template_name,
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
                request=self.request,
                domain_override=domain_override,
                use_https=use_https,
            )
        except Exception as exc:
            _log_email_delivery_failure(exc)

        return redirect(self.get_success_url())


class PasswordResetDoneView(auth_views.PasswordResetDoneView):
    template_name = 'registration/password_reset_done.html'


class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    template_name = 'registration/password_reset_confirm.html'
    success_url = reverse_lazy('accounts:email_login')

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            "Your password has been reset. Sign in with your new password.",
        )
        return response


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
    if (
        user.account_status != CustomUser.AccountStatus.ACTIVE
        or not user.is_active
    ):
        if browser_request:
            return render(request, "accounts/otp_login.html", {"phone": phone, "error": "Your account is inactive. Please contact support."}, status=403)
        return Response({"detail": "Your account is inactive. Please contact support."}, status=status.HTTP_403_FORBIDDEN)
    if profile.pending_phone:
        if browser_request:
            return render(request, "accounts/otp_login.html", {"phone": phone, "error": "Complete or cancel the pending phone change before requesting a login OTP."}, status=409)
        return Response(
            {"detail": "Complete or cancel the pending phone change before requesting a login OTP."},
            status=status.HTTP_409_CONFLICT,
        )

    response_status, detail = _issue_phone_otp(profile.pk, phone)
    if response_status != status.HTTP_200_OK:
        if browser_request:
            return render(
                request,
                "accounts/otp_login.html",
                {"phone": phone, "otp_sent": False, "error": detail},
                status=response_status,
            )
        return Response({"detail": detail}, status=response_status)

    user.phone = phone
    user.save(update_fields=["phone", "updated_at"])

    if browser_request:
        request.session["otp_phone"] = phone
        return redirect("accounts:otp_login_page")
    return Response({"detail": "OTP sent successfully.", "phone": phone})


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def signup_phone_otp_resend(request):
    email = (request.data.get("email") or "").strip()
    phone = normalize_phone_number(str(request.data.get("phone") or "").strip())
    if not email or not phone:
        return Response(
            {"detail": "Email and a valid phone number are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    generic_detail = (
        "Request accepted. If these details match a pending signup, "
        "a verification code may be sent."
    )
    pending_signup = PendingSignup.objects.filter(
        email__iexact=email,
        phone__in=get_phone_variants(phone),
    ).first()
    if pending_signup:
        try:
            result = _request_signup_email_otp(pending_signup.email)
        except Exception as exc:
            _log_email_delivery_failure(exc)
            return Response(
                {"detail": "Unable to send the verification email right now. Please try again later."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        error_response = _signup_email_otp_error_response(result)
        if error_response:
            return error_response
        return Response({"detail": generic_detail}, status=status.HTTP_200_OK)

    user = CustomUser.objects.filter(email__iexact=email).first()
    if not user or (
        user.account_status != CustomUser.AccountStatus.PENDING_VERIFICATION
        or user.is_active
    ):
        return Response({"detail": generic_detail}, status=status.HTTP_200_OK)

    profile = UserProfile.objects.filter(user=user, phone=phone).first()
    if not profile:
        return Response({"detail": generic_detail}, status=status.HTTP_200_OK)

    try:
        result = _request_signup_email_otp(user.email)
    except Exception as exc:
        _log_email_delivery_failure(exc)
        return Response(
            {"detail": "Unable to send the verification email right now. Please try again later."},
            status=status.HTTP_502_BAD_GATEWAY,
        )
    error_response = _signup_email_otp_error_response(result)
    if error_response:
        return error_response
    return Response({"detail": generic_detail}, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def signup_email_otp_resend(request):
    email = (request.data.get("email") or "").strip()
    if not email:
        return Response(
            {"detail": "Email is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    result = _request_signup_email_otp(email)
    error_response = _signup_email_otp_error_response(result)
    if error_response:
        return error_response
    return Response(
        {
            "detail": "If this is an eligible pending signup, an email verification code may be sent."
        },
        status=status.HTTP_200_OK,
    )


@login_required
@require_http_methods(["POST"])
def phone_change_request(request):
    response_status, detail = _start_phone_change(
        request.user, request.POST.get("phone", "")
    )
    if response_status == status.HTTP_200_OK:
        messages.success(request, detail)
    else:
        messages.error(request, detail)
    return redirect("accounts:account_settings")


@login_required
@require_http_methods(["POST"])
def phone_change_verify(request):
    otp = (request.POST.get("otp") or "").strip()
    if not otp:
        messages.error(request, "Enter the verification code.")
        return redirect("accounts:account_settings")

    user, profile, otp_error = _consume_phone_change_otp(request.user.pk, otp)
    if otp_error == "inactive":
        messages.error(request, "Your account is inactive. Please contact support.")
    elif otp_error == "missing":
        messages.error(request, "No phone number is awaiting verification.")
    elif otp_error == "expired":
        messages.error(request, "The code has expired. Request a new one.")
    elif otp_error == "locked":
        messages.error(request, "Too many incorrect codes. Request a new verification code.")
    elif otp_error == "taken":
        messages.error(request, "This phone number is already associated with another account.")
    elif otp_error == "invalid":
        messages.error(request, "The code is invalid.")
    else:
        messages.success(request, "Phone number verified and updated.")
    return redirect("accounts:account_settings")


@login_required
@require_http_methods(["POST"])
def phone_change_resend(request):
    profile = UserProfile.objects.filter(user=request.user).first()
    if not profile or not profile.pending_phone:
        messages.error(request, "No phone number is awaiting verification.")
        return redirect("accounts:account_settings")

    response_status, detail = _start_phone_change(
        request.user, profile.pending_phone
    )
    if response_status == status.HTTP_200_OK:
        messages.success(request, detail)
    else:
        messages.error(request, detail)
    return redirect("accounts:account_settings")


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
    email_form = EmailOTPRequestForm(data={"email": email})
    if not email_form.is_valid():
        return Response(
            {"detail": "Enter a valid email address."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    email = email_form.cleaned_data["email"]
    if not phone:
        return Response({"detail": "Enter a valid phone number."}, status=status.HTTP_400_BAD_REQUEST)
    password_errors = _validate_signup_password(password, email, email)
    if password_errors:
        return Response(
            {"password": password_errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    stage_error = _stage_pending_signup(email, email, password, phone, full_name)
    if stage_error:
        detail = {
            "email_taken": "An account with this email already exists.",
            "phone_taken": "An account with this phone number already exists.",
            "pending_exists": "A signup is already awaiting email verification. Request a new code or verify the existing code.",
        }.get(stage_error, "Unable to start signup. Please try again.")
        return Response(
            {
                "detail": detail,
                "resend_endpoint": reverse("accounts:signup_email_otp_resend"),
            },
            status=(
                status.HTTP_409_CONFLICT
                if stage_error == "pending_exists"
                else status.HTTP_400_BAD_REQUEST
            ),
        )

    email_otp_result = _request_signup_email_otp(email)
    email_otp_error = _signup_email_otp_error_response(email_otp_result)
    if email_otp_error:
        return email_otp_error

    return Response({
        "detail": "Signup received. Verify your email to create your account.",
        "email": email,
        "email_otp_sent": True,
        "email_verification_required": True,
        "verify_endpoint": reverse("accounts:signup_email_otp_verify"),
        "resend_endpoint": reverse("accounts:signup_email_otp_resend"),
        "phone": phone,
    }, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def signup_email_otp_verify(request):
    form = EmailOTPVerifyForm(data=request.data)
    if not form.is_valid():
        return Response(
            {"detail": "A valid email and 6-digit verification code are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        verification = verify_email_otp(
            form.cleaned_data["email"],
            form.cleaned_data["code"],
            EmailOTPChallenge.Purpose.SIGNUP,
        )
    except Exception as exc:
        logger.error(
            "Signup email OTP API verification failed (exception_type=%s)",
            type(exc).__name__,
        )
        return Response(
            {"detail": "We couldn't complete verification right now. Please try again."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    if (
        verification.status == EmailOTPStatus.SUCCESS
        and verification.user is not None
    ):
        user = verification.user
    else:
        if verification.status == EmailOTPStatus.ACCOUNT_CREATION_FAILED:
            return Response(
                {"detail": "We couldn't complete account creation. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return Response(
            {"detail": _email_otp_verification_error(verification.status)},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return Response(
        {
            "detail": "Email verified successfully. You can now log in with your password.",
            "user": UserSerializer(user).data,
        },
        status=status.HTTP_200_OK,
    )


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

    user, profile, otp_error = _consume_phone_otp(
        user.pk, otp, allow_pending_signup=False
    )
    if otp_error == "inactive":
        if browser_request:
            return render(request, "accounts/otp_login.html", {"phone": phone, "otp_sent": True, "error": "Your account is inactive. Please contact support."}, status=403)
        return Response({"detail": "Your account is inactive. Please contact support."}, status=status.HTTP_403_FORBIDDEN)
    if otp_error == "locked":
        if browser_request:
            return render(request, "accounts/otp_login.html", {"phone": phone, "otp_sent": True, "error": "Too many incorrect codes. Request a new OTP."}, status=429)
        return Response({"detail": "Too many incorrect codes. Request a new OTP."}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    if otp_error == "invalid":
        if browser_request:
            return render(request, "accounts/otp_login.html", {"phone": phone, "otp_sent": True, "error": "That OTP is incorrect. Please check the code and try again."}, status=400)
        return Response({"detail": "Invalid OTP."}, status=status.HTTP_400_BAD_REQUEST)
    if otp_error == "expired":
        if browser_request:
            return render(request, "accounts/otp_login.html", {"phone": phone, "otp_sent": True, "error": "This OTP has expired. Please request a new one."}, status=400)
        return Response({"detail": "OTP has expired. Please request a new one."}, status=status.HTTP_400_BAD_REQUEST)

    if browser_request:
        request.session.pop("otp_phone", None)
        auth_login(request, user)
        return redirect("accounts:dashboard_page")
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
        next_url = request.POST.get("next") or request.GET.get("next") or ""
        safe_next_url = _safe_next_url(request, next_url)

        if not email or not password:
            return render(request, "accounts/auth.html", {"active_tab": "login", "error": "Email and password are required.", "next": safe_next_url})

        user = CustomUser.objects.filter(email__iexact=email).first()
        if not user:
            return render(request, "accounts/auth.html", {"active_tab": "login", "error": "Invalid email or password.", "next": safe_next_url})

        if (
            user.account_status == CustomUser.AccountStatus.PENDING_VERIFICATION
            and not user.is_active
            and not user.is_email_verified
        ):
            if not user.check_password(password):
                return render(request, "accounts/auth.html", {"active_tab": "login", "error": "Invalid email or password.", "next": safe_next_url})

            request.session["signup_email_verification_email"] = user.email
            request.session["contact_verification_next"] = safe_next_url
            request.session["contact_verification_remember"] = bool(
                request.POST.get("remember")
            )
            return redirect("accounts:signup_email_verify")

        if (
            user.account_status != CustomUser.AccountStatus.ACTIVE
            or not getattr(user, "is_active", True)
        ):
            if not user.check_password(password):
                return render(request, "accounts/auth.html", {"active_tab": "login", "error": "Invalid email or password.", "next": safe_next_url})
            return render(request, "accounts/auth.html", {"active_tab": "login", "error": "Your account is inactive. Please contact support.", "next": safe_next_url})

        if not user.is_email_verified:
            if not user.check_password(password):
                return render(request, "accounts/auth.html", {"active_tab": "login", "error": "Invalid email or password.", "next": safe_next_url})
            return render(
                request,
                "accounts/auth.html",
                {
                    "active_tab": "login",
                    "error": "Verify your email before logging in.",
                    "next": safe_next_url,
                },
            )

        authenticated_user = authenticate(request, username=user.email, password=password)
        if authenticated_user is None:
            return render(request, "accounts/auth.html", {"active_tab": "login", "error": "Invalid email or password.", "next": safe_next_url})

        if (
            user.account_status != CustomUser.AccountStatus.ACTIVE
            or not user.is_active
        ):
            return render(request, "accounts/auth.html", {"active_tab": "login", "error": "Your account is inactive. Please contact support.", "next": safe_next_url})

        auth_login(request, authenticated_user)
        if request.POST.get("remember"):
            request.session.set_expiry(settings.SESSION_COOKIE_AGE)
        else:
            request.session.set_expiry(0)

        if safe_next_url:
            return redirect(safe_next_url)

        # Redirect users by role: owner -> owner dashboard, vendor -> seller dashboard, else customer dashboard
        if getattr(authenticated_user, "is_owner", False):
            return redirect("sellers:owner_dashboard")
        if getattr(authenticated_user, "is_vendor", False):
            return redirect("sellers:dashboard")
        return redirect("accounts:dashboard_page")

    return render(
        request,
        "accounts/auth.html",
        {
            "active_tab": "login",
            "next": _safe_next_url(request, request.GET.get("next", "")),
        },
    )


def _safe_next_url(request, next_url):
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return ""


def _email_otp_verification_error(verification_status):
    if verification_status == EmailOTPStatus.INCORRECT:
        return (
            "Incorrect OTP. Please enter the correct OTP. "
            "If you requested a replacement, use the latest code."
        )
    if verification_status == EmailOTPStatus.EXPIRED:
        return "This verification code has expired. Request a new code."
    if verification_status == EmailOTPStatus.LOCKED:
        return "Too many incorrect codes. Request a new verification code."
    if verification_status == EmailOTPStatus.ACCOUNT_CREATION_FAILED:
        return "We couldn't complete account creation. Please try again."
    return "This verification code is no longer available. Request a new code."


def _safe_contact_verification_next(request):
    return _safe_next_url(
        request,
        request.session.get("contact_verification_next", ""),
    )


def _finish_contact_verification(request, user):
    if not user.is_email_verified:
        return None

    next_url = _safe_contact_verification_next(request)
    remember = request.session.pop("contact_verification_remember", False)
    request.session.pop("contact_verification_user_id", None)
    request.session.pop("contact_verification_next", None)
    auth_login(request, user, backend=settings.AUTHENTICATION_BACKENDS[0])
    request.session.set_expiry(
        settings.SESSION_COOKIE_AGE if remember else 0
    )

    if next_url:
        return redirect(next_url)
    if user.is_owner:
        return redirect("sellers:owner_dashboard")
    if user.is_vendor:
        return redirect("sellers:dashboard")
    return redirect("accounts:dashboard_page")


@require_http_methods(["GET", "POST"])
def verify_contacts(request):
    return redirect("accounts:email_login")


def logout_view(request):
    auth_logout(request)
    return redirect("home")


def signup_form_view(request):
    form = SignupForm(request.POST or None)
    next_url = _safe_next_url(
        request,
        request.POST.get("next") or request.GET.get("next", ""),
    )
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        password = form.cleaned_data["password"]
        phone = form.cleaned_data["phone"]
        full_name = form.cleaned_data["full_name"].strip()

        if PendingSignup.objects.filter(email__iexact=email).exists():
            request.session["signup_email_verification_email"] = email
            request.session["contact_verification_next"] = next_url
            request.session["contact_verification_remember"] = False
            request.session["signup_email_verification_notice"] = (
                "A signup is already awaiting verification. Enter the code or request another one."
            )
            return redirect("accounts:signup_email_verify")

        stage_error = _stage_pending_signup(
            email,
            email,
            password,
            phone,
            full_name,
        )
        if stage_error:
            form.add_error(
                None,
                "An account with this email or phone number already exists. Please log in or check your details.",
            )
            return render(
                request,
                "accounts/auth.html",
                {"active_tab": "signup", "form": form, "next": next_url},
                status=400,
            )

        request.session["signup_email_verification_email"] = email
        request.session["contact_verification_next"] = next_url
        request.session["contact_verification_remember"] = False
        result = _request_signup_email_otp(email)
        if result == "throttled":
            request.session["signup_email_verification_notice"] = (
                "Please wait before requesting another verification code."
            )
        elif result == "delivery_failed":
            request.session["signup_email_verification_notice"] = (
                "Unable to send the verification email right now. "
                "Please wait a minute and try again."
            )
        else:
            request.session["signup_email_verification_notice"] = (
                "A verification code has been sent to your email. "
                "It expires in 10 minutes."
            )
        return redirect("accounts:signup_email_verify")

    return render(
        request,
        "accounts/auth.html",
        {"active_tab": "signup", "form": form, "next": next_url},
    )


@require_http_methods(["GET", "POST"])
def signup_email_verify(request):
    email = request.session.get("signup_email_verification_email", "")
    if not email:
        return redirect("accounts:signup_form")

    form = EmailOTPVerifyForm(request.POST or None, initial={"email": email})
    error = ""
    if request.method == "POST":
        if form.is_valid() and form.cleaned_data["email"].casefold() == email.casefold():
            try:
                verification = verify_email_otp(
                    email,
                    form.cleaned_data["code"],
                    EmailOTPChallenge.Purpose.SIGNUP,
                )
                if verification.status == EmailOTPStatus.SUCCESS:
                    user = verification.user
                    request.session.pop("signup_email_verification_email", None)
                    request.session.pop("signup_email_verification_notice", None)
                    request.session["contact_verification_user_id"] = user.pk
                    response = _finish_contact_verification(request, user)
                    if response:
                        return response
                    return redirect("accounts:email_login")
                error = _email_otp_verification_error(verification.status)
            except Exception as exc:
                logger.error(
                    "Signup email verification request failed (exception_type=%s)",
                    type(exc).__name__,
                )
                return site_views.server_error(request)
        elif form.is_valid():
            error = "Use the email address associated with this verification request."

    return render(
        request,
        "accounts/signup_email_verify.html",
        {
            "email": email,
            "form": form,
            "error": error,
            "notice": request.session.pop("signup_email_verification_notice", ""),
        },
    )


@require_http_methods(["POST"])
def signup_email_verify_resend(request):
    email = request.session.get("signup_email_verification_email", "")
    if not email:
        return redirect("accounts:signup_form")

    try:
        result = request_email_otp(email, EmailOTPChallenge.Purpose.SIGNUP)
        if result == "throttled":
            request.session["signup_email_verification_notice"] = (
                "Please wait before requesting another verification code."
            )
        else:
            request.session["signup_email_verification_notice"] = (
                "A new verification code has been sent to your email."
            )
    except Exception as exc:
        _log_email_delivery_failure(exc)
        request.session["signup_email_verification_notice"] = (
            "Unable to send the verification email right now. "
            "Please wait a minute and try again."
        )
    return redirect("accounts:signup_email_verify")


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
    return render(
        request,
        "accounts/auth.html",
        {
            "active_tab": "login",
            "next": _safe_next_url(request, request.GET.get("next", "")),
        },
    )


def signup_page(request):
    return render(
        request,
        "accounts/auth.html",
        {
            "active_tab": "signup",
            "next": _safe_next_url(request, request.GET.get("next", "")),
        },
    )


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


def _log_email_delivery_failure(exc):
    failure_class, smtp_code = classify_email_delivery_error(exc)
    safe_details = {
        "email_configuration": "Email delivery configuration is incomplete or invalid",
        "brevo_unauthorized": "Brevo returned HTTP 401 Unauthorized",
        "brevo_forbidden": "Brevo returned HTTP 403 Forbidden",
        "brevo_api_rejected": "Brevo rejected the API request",
        "brevo_malformed_response": "Brevo returned an invalid response",
        "brevo_timeout": "Brevo API request timed out",
        "brevo_connection": "Could not connect to Brevo API",
        "database_operational": "Database operation failed",
        "smtp_authentication": "SMTP authentication failed",
        "smtp_connection": "SMTP connection failed",
        "smtp_disconnected": "SMTP server disconnected",
        "smtp_recipient_rejected": "SMTP recipient was rejected",
        "smtp_sender_rejected": "SMTP sender was rejected",
        "smtp_response": "SMTP server returned an error",
        "network_or_timeout": "Network operation failed or timed out",
        "email_backend": "Email backend failed",
    }
    safe_detail = safe_details.get(
        failure_class,
        "Email delivery failed; no safe detail available",
    )
    logger.error(
        "Account email delivery failed: provider=%s backend=%s "
        "brevo_api_key_configured=%s brevo_sender_configured=%s "
        "host_configured=%s port=%s tls=%s ssl=%s "
        "username_configured=%s password_configured=%s sender_configured=%s "
        "failure_class=%s safe_detail=%s status_code=%s error_type=%s "
        "brevo_error_code=%s brevo_error_message=%s",
        settings.EMAIL_PROVIDER or "unset",
        settings.EMAIL_BACKEND,
        bool(settings.BREVO_API_KEY),
        bool(settings.BREVO_SENDER_EMAIL),
        bool(settings.EMAIL_HOST),
        settings.EMAIL_PORT,
        settings.EMAIL_USE_TLS,
        settings.EMAIL_USE_SSL,
        bool(settings.EMAIL_HOST_USER),
        bool(settings.EMAIL_HOST_PASSWORD),
        bool(settings.DEFAULT_FROM_EMAIL),
        failure_class,
        safe_detail,
        smtp_code,
        type(exc).__name__,
        getattr(exc, "response_code", None),
        getattr(exc, "response_message", None),
    )


def _email_otp_request(request, purpose, verify_url_name, template_name):
    form = EmailOTPRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        try:
            request_email_otp(email, purpose)
        except Exception as exc:
            _log_email_delivery_failure(exc)

        request.session["email_otp_email"] = email
        next_url = request.POST.get("next", "")
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            request.session["email_otp_next"] = next_url
        else:
            request.session.pop("email_otp_next", None)
        request.session["email_otp_notice"] = (
            "If an eligible account exists, a code will be sent. "
            "If you requested one recently, wait before trying again."
        )
        return redirect(verify_url_name)

    return render(
        request,
        template_name,
        {
            "form": form,
            "phase": "request",
            "next": request.POST.get("next") or request.GET.get("next", ""),
        },
    )


@require_http_methods(["GET", "POST"])
def email_otp_login_page(request):
    return redirect("accounts:email_login")


@require_http_methods(["GET", "POST"])
def email_otp_login_verify(request):
    return redirect("accounts:email_login")


@require_http_methods(["GET", "POST"])
def password_reset_otp_page(request):
    return _email_otp_request(
        request,
        EmailOTPChallenge.Purpose.PASSWORD_RESET,
        "accounts:password_reset_otp_verify",
        "accounts/password_reset_otp.html",
    )


@require_http_methods(["GET", "POST"])
def password_reset_otp_verify(request):
    email = request.session.get("email_otp_email", "")
    if not email:
        return redirect("accounts:password_reset_otp")

    form = EmailOTPVerifyForm(
        request.POST or None,
        initial={"email": email},
    )
    error = ""
    if request.method == "POST":
        if form.is_valid() and form.cleaned_data["email"].casefold() == email.casefold():
            verification = verify_email_otp(
                email,
                form.cleaned_data["code"],
                EmailOTPChallenge.Purpose.PASSWORD_RESET,
            )
            if (
                verification.status == EmailOTPStatus.SUCCESS
                and verification.user is not None
            ):
                user = verification.user
                request.session.cycle_key()
                request.session["password_reset_otp_user_id"] = user.pk
                request.session["password_reset_otp_expires"] = (
                    timezone.now() + timedelta(minutes=10)
                ).timestamp()
                request.session.pop("email_otp_email", None)
                request.session.pop("email_otp_notice", None)
                return redirect("accounts:password_reset_otp_new")
        error = "That code is invalid or expired. Request a new code and try again."

    return render(
        request,
        "accounts/password_reset_otp.html",
        {
            "phase": "verify",
            "email": email,
            "form": form,
            "error": error,
            "notice": request.session.get("email_otp_notice", ""),
        },
    )


@require_http_methods(["GET", "POST"])
def password_reset_otp_new(request):
    user_id = request.session.get("password_reset_otp_user_id")
    expires = request.session.get("password_reset_otp_expires", 0)
    user = CustomUser.objects.filter(pk=user_id, is_active=True).first() if user_id else None
    if not user or timezone.now().timestamp() >= expires:
        request.session.pop("password_reset_otp_user_id", None)
        request.session.pop("password_reset_otp_expires", None)
        messages.error(request, "Please verify a new password reset code.")
        return redirect("accounts:password_reset_otp")

    form = SetPasswordForm(user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        request.session.pop("password_reset_otp_user_id", None)
        request.session.pop("password_reset_otp_expires", None)
        if request.user.is_authenticated:
            auth_logout(request)
        messages.success(
            request,
            "Your password has been reset. Sign in with your new password.",
        )
        return redirect("accounts:email_login")

    return render(
        request,
        "accounts/password_reset_otp.html",
        {"phase": "set_password", "form": form},
    )


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
