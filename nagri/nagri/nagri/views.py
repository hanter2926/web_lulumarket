from django.shortcuts import render
from django.http import HttpResponse, Http404
from django.conf import settings
import os


def bad_request(request, exception=None):
    return render(request, "errors/400.html", status=400)


def permission_denied(request, exception=None):
    return render(request, "errors/403.html", status=403)


def page_not_found(request, exception=None):
    return render(request, "errors/404.html", status=404)


def server_error(request):
    return render(request, "errors/500.html", status=500)


def service_worker(request):
    """Serve the service worker JS at the site root so it can take scope "/".
    The file is located under static/js/service-worker.js in the project.
    """
    sw_path = os.path.join(settings.BASE_DIR, 'static', 'js', 'service-worker.js')
    if not os.path.exists(sw_path):
        raise Http404
    with open(sw_path, 'rb') as fh:
        content = fh.read()
    return HttpResponse(content, content_type='application/javascript')
