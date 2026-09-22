from django.db.models import Q

from .models import FraudSignal, LoginHistory


def scan_user_login_risk(user):
    failed_count = LoginHistory.objects.filter(
        user=user,
        status=LoginHistory.Status.FAILED,
    ).count()
    suspicious_count = LoginHistory.objects.filter(
        user=user,
        is_suspicious=True,
    ).count()
    score = min(100, failed_count * 10 + suspicious_count * 25)
    if score < 25:
        return None
    severity = FraudSignal.Severity.HIGH if score >= 70 else FraudSignal.Severity.MEDIUM
    return FraudSignal.objects.create(
        user=user,
        category="LOGIN_RISK",
        severity=severity,
        score=score,
        reason=f"{failed_count} failed and {suspicious_count} suspicious login events detected.",
    )
