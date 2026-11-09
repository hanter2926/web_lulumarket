# Deployment checklist

1. Create a Python 3.14 virtual environment and install `requirements.txt`.
2. Set `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=False`, `DJANGO_ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, and all `MYSQL_*` variables.
3. Set `DJANGO_SECURE_SSL_REDIRECT=true` only when the reverse proxy terminates HTTPS and forwards the correct protocol.
4. Run `python manage.py check --deploy`.
5. Run `python manage.py migrate` only during an approved deployment window.
6. Serve static files through the web server or object storage. Do not expose `MEDIA_ROOT` publicly.
7. Run the application behind a production WSGI/ASGI server and reverse proxy.
8. Configure a process supervisor and monitor `GET /health/`. A healthy response is `{"status":"ok","database":"ok"}`; database failure returns HTTP 503.
9. Preserve the pypdfium2 license directory listed in `THIRD_PARTY_NOTICES.md`.

PDF rendering is isolated in a child process. The parent enforces a hard worker timeout and process-local concurrency of two. Linux workers additionally apply CPU and address-space limits. Windows native memory limits are not claimed by Phase 1.
