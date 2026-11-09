from django.core.cache import cache


LOGIN_FAILURE_LIMIT = 5
LOGIN_IP_FAILURE_LIMIT = 20
PASSWORD_RESET_REQUEST_LIMIT = 3
PASSWORD_RESET_IP_REQUEST_LIMIT = 10
RATE_LIMIT_WINDOW_SECONDS = 15 * 60


def client_address(request):
    return request.META.get("REMOTE_ADDR") or "unknown"


def _increment(key, limit):
    if not cache.add(key, 1, RATE_LIMIT_WINDOW_SECONDS):
        try:
            count = cache.incr(key)
        except ValueError:
            cache.set(key, 1, RATE_LIMIT_WINDOW_SECONDS)
            count = 1
    else:
        count = 1
    return count <= limit


def _under_limit(key, limit):
    return (cache.get(key) or 0) < limit


def allow_login_attempt(request, identifier):
    address = client_address(request)
    normalized = identifier.casefold()
    return _under_limit(
        f"suhana:login:identifier:{address}:{normalized}",
        LOGIN_FAILURE_LIMIT,
    ) and _under_limit(f"suhana:login:ip:{address}", LOGIN_IP_FAILURE_LIMIT)


def record_login_failure(request, identifier):
    address = client_address(request)
    normalized = identifier.casefold()
    _increment(
        f"suhana:login:identifier:{address}:{normalized}",
        LOGIN_FAILURE_LIMIT,
    )
    _increment(f"suhana:login:ip:{address}", LOGIN_IP_FAILURE_LIMIT)


def allow_password_reset_request(request, email):
    address = client_address(request)
    normalized = email.casefold()
    email_allowed = _increment(
        f"suhana:reset:email:{normalized}",
        PASSWORD_RESET_REQUEST_LIMIT,
    )
    ip_allowed = _increment(
        f"suhana:reset:ip:{address}",
        PASSWORD_RESET_IP_REQUEST_LIMIT,
    )
    return email_allowed and ip_allowed


def clear_login_attempts(request, identifier):
    address = client_address(request)
    normalized = identifier.casefold()
    cache.delete(f"suhana:login:identifier:{address}:{normalized}")
