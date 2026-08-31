import logging
from django.http import HttpResponseServerError


class AdminSafetyMiddleware:
    """Middleware to safely guard requests to Django admin paths.

    - Catches unexpected exceptions while handling admin requests and logs them.
    - Safely checks `request.user` attributes (avoids AttributeError when anonymous).
    - Returns a friendly 500 response instead of allowing an internal crash to bubble up.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.logger = logging.getLogger(__name__)

    def __call__(self, request):
        path = request.path or ''
        # Only apply safeguards to admin URLs to avoid changing non-admin behavior
        if path.startswith('/admin'):
            try:
                # Safe user inspection: avoid accessing attributes on None
                user = getattr(request, 'user', None)
                # Access `is_staff` only if present, default to False
                _is_staff = False
                try:
                    _is_staff = bool(getattr(user, 'is_staff', False))
                except Exception:
                    # Defensive: log but do not raise
                    self.logger.debug('Unable to determine user.is_staff for admin request')

                # Continue with normal request processing
                response = self.get_response(request)
                return response
            except Exception as exc:
                # Log complete exception details for debugging
                self.logger.exception('Unhandled exception while processing admin request: %s', exc)
                # Return a friendly, non-sensitive server error page
                return HttpResponseServerError('Something went wrong while loading the admin interface. The error has been logged.')

        # Non-admin paths are unaffected
        return self.get_response(request)
