from functools import wraps
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect


def owner_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        user = getattr(request, 'user', None)
        if not (user and user.is_authenticated and getattr(user, 'is_owner', False)):
            # If not authenticated, redirect to login page, else raise permission denied
            if not (user and user.is_authenticated):
                return redirect('login_page')
            raise PermissionDenied()
        return view_func(request, *args, **kwargs)

    return _wrapped
