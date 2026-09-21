from .models import LoginHistory

def check_suspicious_login(user, request, current_ip):
    reasons = []
    
    # 1. Unknown IP or Location Detection
    previous_logins = LoginHistory.objects.filter(user=user, status=LoginHistory.Status.SUCCESS)
    known_ips = previous_logins.values_list('ip_address', flat=True).distinct()
    
    if known_ips.exists() and current_ip not in known_ips:
        reasons.append("New/Unrecognized IP Address detected.")
        
    # 2. Frequent Failure Detection (Brute-force indicator)
    recent_failed = LoginHistory.objects.filter(
        user=user, 
        status=LoginHistory.Status.FAILED
    ).order_by('-timestamp')[:5]
    
    if recent_failed.count() >= 5:
        reasons.append("Multiple failed login attempts prior to success.")
        
    return len(reasons) > 0, ", ".join(reasons)