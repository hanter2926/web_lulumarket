# AccountBazaar deployment checklist

This project is a Django application. The included `Procfile` starts Gunicorn with `accountbazaar.wsgi:application`.

## Before deployment

1. Create a managed PostgreSQL database.
2. Configure `DJANGO_SECRET_KEY` with a long random value.
3. Set `DEBUG=False` and `DEMO_PAYMENTS_ENABLED=False`.
4. Set `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` to the real domains.
5. Set `DATABASE_URL` to the managed PostgreSQL connection string.
6. Configure `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, and `RAZORPAY_WEBHOOK_SECRET` in the hosting secret manager.
7. Configure `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, and `DEFAULT_FROM_EMAIL` if email is enabled.
8. Use private object storage for `MEDIA_ROOT` content. Set `USE_S3=True` and the `AWS_*` variables when using S3-compatible storage.

## Release commands

```text
python manage.py check --deploy
python manage.py migrate
python manage.py collectstatic --noinput
```

Run Gunicorn through the hosting platform's process manager or the included Procfile. Do not run Django's development server in production.

## Required verification

1. Confirm HTTPS and domain routing.
2. Confirm login and logout.
3. Create and inspect a seller listing.
4. Complete a buyer checkout with a real Razorpay payment.
5. Confirm the signed Razorpay webhook is configured and received.
6. Verify secure handoff and buyer confirmation.
7. Verify dispute creation and moderator access.
8. Verify `Payout Eligible` status.
9. Confirm that no payout is shown as transferred: seller payout is currently **Payout Eligible, not an actual money transfer**.
10. Check logs for errors without logging secrets or credentials.

## Current limitations

- Seller payout is not integrated with Razorpay Route. Route activation, seller Linked Account onboarding, provider transfer calls, and transfer webhooks are still required.
- Local filesystem media is not durable across ephemeral hosting instances. Use private persistent object storage for listing images, KYC documents, seller documents, and dispute evidence.
- Uploaded private documents must be served through an authorization-checked download flow or private signed URLs; never expose the media bucket publicly.
- Razorpay production credentials and webhook configuration are hosting/provider prerequisites.
