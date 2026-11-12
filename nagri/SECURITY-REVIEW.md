# Nagri DRF and Simple JWT Security Audit

**Review type:** Strict read-only source audit
**Scope:** Django REST Framework, Simple JWT, API authorization and ownership, token handling, and source-visible abuse protections
**Runtime verification:** Not performed

## Executive summary

The source review found four issues requiring attention:

1. A fixed insecure fallback value is used for Django's `SECRET_KEY` when `DJANGO_SECRET_KEY` is absent. This is a high-impact deployment risk, but whether production uses the fallback is **not verified**.
2. API logout ends the Django session but does not revoke issued JWTs.
3. Authenticated customers can mutate or delete their own order-item records through the API.
4. Public phone OTP/login responses disclose whether a phone number has an account.

The global DRF permission default is `AllowAny`; reviewed sensitive viewsets generally set explicit authentication requirements and scope querysets to the user or role. No database/API tests or production checks were performed. Deployment environment overrides and external API clients were not inspected.

## Findings

| # | Severity | File | Lines | Vulnerability | Confidence |
|---|----------|------|-------|---------------|------------|
| 1 | 🟠 HIGH | `nagri/common_settings.py` | 19-25, 60, 159-167 | Fixed insecure `SECRET_KEY` fallback can also be the Simple JWT signing key when `DJANGO_SECRET_KEY` is missing. Fallback use in production is not verified. | 9/10 |
| 2 | 🟡 MEDIUM | `accounts/views.py`; `nagri/common_settings.py` | `accounts/views.py`: 646-650, 692-702; `common_settings.py`: 164-167 | Logout does not revoke already issued JWTs. The configured access-token lifetime is seven days. | 9/10 |
| 3 | 🟡 MEDIUM | `orders/views.py`; `orders/serializers.py`; `orders/urls.py` | `views.py`: 978-985; `serializers.py`: 8-14; `urls.py`: 11-13 | Authenticated customers can update or delete their own order items; writable quantity and price can undermine order integrity. | 9/10 |
| 4 | ⚪ LOW | `accounts/views.py` | 653-668, 964-1013 | Public phone authentication responses distinguish registered from unregistered phone numbers, enabling account enumeration. | 9/10 |

### 1. Possible signing-key fallback exposure — HIGH

`build_common_settings()` reads `DJANGO_SECRET_KEY` and uses a fixed insecure fallback if it is absent (`nagri/common_settings.py:19-25`). The chosen value is assigned to Django's `SECRET_KEY` (`nagri/common_settings.py:60`). The project enables JWT authentication, and its `SIMPLE_JWT` dictionary does not define a separate signing key (`nagri/common_settings.py:159-168`).

**Risk:** If a deployed environment omits `DJANGO_SECRET_KEY`, the known fallback may allow forged Django signatures and JWTs, depending on the library defaults and deployment behavior.

**Status:** The unsafe fallback is confirmed in source. Whether a deployed environment uses it is **not verified**; no secret values or `.env` values were inspected.

**Minimum safe remediation:** Fail startup when a strong, explicitly provided secret is absent. Consider a separately managed high-entropy JWT signing key. If the fallback has ever been used, rotate signing material and invalidate affected tokens.

**Runtime verification required:** Confirm the effective production key is explicitly configured without revealing it; confirm old tokens cannot be accepted after a rotation.

### 2. JWTs remain valid after logout — MEDIUM

Password and phone login flows return access and refresh tokens (`accounts/views.py:622-650`, `653-696`). API logout calls Django `auth_logout()` and returns success (`accounts/views.py:699-702`), but no JWT blacklist or other revocation call is present. The configured lifetimes are seven days for access tokens and thirty days for refresh tokens (`nagri/common_settings.py:164-168`).

**Risk:** A copied bearer token can remain usable after the associated Django session is logged out, until token expiry. Django session logout alone does not revoke that token.

**Minimum safe remediation:** Adopt a supported server-side JWT revocation/blacklist design and revoke refresh credentials on logout. Use a short access-token lifetime appropriate to the application.

**Runtime verification required:** With controlled test credentials only, verify that issued credentials are rejected after logout. No tokens were generated or tested during this audit.

### 3. Customer order-item mutations — MEDIUM

`OrderItemViewSet` is a `ModelViewSet` with authenticated access and a queryset scoped to the requesting user's orders except for staff (`orders/views.py:978-985`). The serializer leaves fields including `quantity` and `price` writable (`orders/serializers.py:8-14`), and the router exposes the viewset (`orders/urls.py:11-13`).

**Risk:** A customer may alter or delete line items belonging to their own order. This is not cross-customer BOLA in the inspected queryset, but can cause inconsistencies between item details, paid totals, invoices, and fulfillment.

**Minimum safe remediation:** Make customer-facing order-item operations read-only or remove customer mutation routes. Keep any necessary administrative correction in a separately authorized workflow.

**Runtime verification required:** Confirm deployed methods and downstream reliance on order-item values in a controlled environment. No API requests were made.

### 4. Phone-number account enumeration — LOW

Public phone OTP request/login paths return different responses for numbers with and without matching accounts (`accounts/views.py:653-668`, `964-1013`).

**Risk:** A caller can determine which candidate phone numbers have accounts, potentially facilitating targeted phishing or unwanted contact.

**Minimum safe remediation:** Normalize public response bodies and status behavior so account existence is not disclosed, while preserving the OTP delivery and verification flow.

**Runtime verification required:** Compare observable status, response content, and timing for registered and unregistered numbers in a controlled environment. No endpoints were called.

## Priority list

1. Require explicit, strong signing material; determine whether the fixed fallback has ever been used in deployment.
2. Add JWT revocation semantics to logout.
3. Prevent customer-side order-item mutation.
4. Normalize public phone-authentication responses.
5. Treat the seven-day access-token lifetime as an exposure multiplier until revocation exists.
6. Verify production has an explicit signing key, without exposing its value.
7. Verify whether external API clients store tokens securely; repository frontend inspection does not cover external clients.
8. Review deployed proxy/CORS behavior; source configuration alone did not establish an exploit path.
9. Verify production `DEBUG` and secure-cookie settings.
10. Verify whether deployment gateways or controls add protections not represented in repository source.

Items 5-10 are impact or verification priorities, not additional confirmed vulnerabilities.

## JWT and DRF configuration

Source settings are defined in `nagri/common_settings.py:147-168`; `nagri/settings.py:18-23,56-61` assembles settings in two phases. This describes repository configuration, not deployed effective values.

| Setting | Source configuration |
|---|---|
| DRF default permission | `AllowAny` (`common_settings.py:147-150`) |
| Authentication classes | `SessionAuthentication`, `JWTAuthentication` (`common_settings.py:159-162`) |
| Access-token lifetime | Seven days (`common_settings.py:165`) |
| Refresh-token lifetime | Thirty days (`common_settings.py:166`) |
| Authorization header type | `Bearer` (`common_settings.py:167`) |
| Signing-key source | No separate Simple JWT signing key is declared; library default applies. Django `SECRET_KEY` comes from `DJANGO_SECRET_KEY` or the fixed fallback (`common_settings.py:19-25,60,164-168`). |
| Algorithm, verifying key, refresh rotation, blacklist-after-rotation, audience, issuer, leeway | Not explicitly set in the project `SIMPLE_JWT` dictionary (`common_settings.py:164-168`). Standard library defaults are not treated as verified because the installed library version/runtime configuration was not checked. |
| Global DRF throttling / pagination | No global throttle or pagination class appears in the inspected DRF configuration (`common_settings.py:147-162`). No per-view throttle/pagination classes were found in the reviewed viewsets. |
| Renderers / parsers | JSON renderer; JSON, form, and multipart parsers (`common_settings.py:151-158`). |

## API access and ownership protections observed

- Cart viewsets use authenticated permissions and user-scoped querysets (`cart/views.py:18-23,49-54`).
- Wishlist viewsets use authenticated permissions and user-scoped querysets (`wishlist/views.py:16-23`).
- Order viewsets scope access to the requesting user's orders, with staff handling (`orders/views.py:746-753`).
- Address and payment-method viewsets filter by user and require authenticated access (`accounts/views.py:902-931`).
- Seller resource viewsets use authentication and role/owner-scoped querysets (`sellers/views.py:210-257`). Area, incident, and route-issue endpoints use custom permissions (`sellers/views.py:143-204`).
- Product/category APIs use a staff-write/read-only permission (`products/views.py:104-133`).
- User creation, login, and OTP endpoints intentionally include public `AllowAny` paths (`accounts/views.py:459-462,547,622-623,653-654,964-965`).
- Public product reads are consistent with the global `AllowAny` default; every API endpoint should be reviewed as new routes are added.
- The order-item queryset is owner-scoped, but writable serializer fields permit the customer-side integrity issue listed above.

## Token handling and abuse protections

- Login and OTP verification issue access/refresh tokens in API responses (`accounts/views.py:622-650,653-696,1484-1490`).
- API logout and browser logout end Django sessions; the inspected flows do not revoke JWTs (`accounts/views.py:699-702,1656-1658`).
- No token refresh, blacklist, or rotation endpoint was found in the inspected project routes/source.
- No JWT storage or `Authorization: Bearer` transmission was found in the inspected frontend JavaScript. External API clients and deployed frontend behavior are **not verified**.
- Django CSRF middleware is present in the middleware stack (`nagri/common_settings.py:74-82`); browser code adds CSRF headers for relevant requests (`static/js/base/main.js:7-11`). Session-authenticated unsafe requests therefore retain Django's CSRF protections.
- Email OTP source includes per-IP request-window limits, a resend cooldown, and attempt limits (`accounts/email_otp.py:23-27`).
- Phone OTP verification has attempt limits (`accounts/views.py:70,124-156`).
- DRF-wide and per-view API throttling were not found in reviewed settings/viewsets. This is a source-level gap to assess for public login/OTP/API endpoints, not evidence that no infrastructure-level rate limiting exists.
- Product listing has separate template pagination (`products/views.py:77`); this does not establish DRF API pagination.

## Verification limits

Not verified:

- Effective production environment settings, including whether the fallback secret is used.
- Installed Simple JWT version and library defaults for omitted JWT settings.
- Deployed proxy, CORS, cookie, rate-limit, and gateway behavior.
- External clients' token storage or logout behavior.
- Runtime API authorization, expiry, refresh, or revocation behavior.
- Database contents, production data relationships, and downstream order/fulfillment effects.

## Recommended implementation sequence

1. Require explicit strong signing material; verify configuration and rotate/invalidate keys safely if needed.
2. Choose a JWT revocation design and short access-token lifetime; implement logout revocation.
3. Make customer order-item routes read-only while preserving any privileged correction workflow.
4. Normalize phone OTP/login responses to avoid account enumeration.
5. Add focused tests for owner scoping, rejected order-item mutations, logout revocation, and indistinguishable phone-auth responses.
6. Separately authorize controlled non-production runtime verification.

## Audit confirmation

This report records static source inspection only. No files were modified during the audit, no database was accessed, no API was called, no JWT was generated or revoked, and no external or production system was contacted. Secret values were not inspected or disclosed. Runtime verification and penetration testing were not performed.
