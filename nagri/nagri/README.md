# 🛍️ NAGRI - Multi-Vendor E-Commerce Marketplace

NAGRI is a modern **Django-based E-Commerce and Multi-Seller Marketplace** platform.

The platform allows customers to browse products, add items to their cart, apply discounts, place orders, and make payments using multiple payment methods.

It also includes a complete **Seller Marketplace System** where users can apply to become sellers, verify their email using OTP, upload documents, select product categories, and wait for owner/admin approval.

Approved sellers can manage their own products, orders, sales, and reports through a dedicated seller dashboard.

---

## 🌐 Live Website

🚀 **Live Demo:**

https://web-lulumarket.onrender.com

---

# ✨ Features

## 👤 Customer Features

- User Registration with email OTP verification and Login
- Custom User Authentication
- Email-based Login
- Password Reset
- Product Browsing
- Category and Subcategory Browsing
- Product Search
- Shopping Cart
- Wishlist
- Product Quantity Management
- Checkout System
- Delivery Method Selection
- Coupon / Discount Support
- Order Review
- Multiple Payment Methods
- Order History
- Secure Checkout

## Email and Phone Verification

New accounts must verify their email address before finishing signup. Email OTPs expire after 10 minutes, can be resent every 30 seconds, and are limited to 30 requests per email and purpose per hour. Verification is locked after five incorrect attempts. Phone verification remains available separately.

Email verification codes are sent during new-account registration, not during password login. Users sign in with their email address and password; email OTP remains available for password recovery.

Production email uses the existing Brevo HTTPS API integration, not SMTP. Set these Render environment variables:

```text
BREVO_API_KEY=<your Brevo API key>
BREVO_SENDER_EMAIL=<an active, verified sender in your Brevo account>
BREVO_SENDER_NAME=NAGRI
```

The sender address must match the active, verified sender in Brevo. Account OTP and password-reset email use the existing direct Brevo API helper; other Django mail uses Anymail's Brevo API backend. Local development uses Django's console backend when `DEBUG=True`. Resend is not selected for production because this project does not control a verified sending domain there.

For local development, set `DEBUG=True` to enable Django's development-only routes for files under `MEDIA_ROOT`. Keep `DEBUG=False` in production and use the configured production media storage for uploaded product images.

Brevo API requests use a 5-second connect timeout and 30-second response timeout through Anymail's `ANYMAIL["REQUESTS_TIMEOUT"]` setting. The direct account-OTP helper uses the same timeout. Automatic retries are intentionally disabled because a response timeout can happen after Brevo has accepted the email; the generated OTP remains valid in that case.

Remove any `EMAIL_PROVIDER=resend` or `EMAIL_BACKEND` override from Render so production uses the Brevo HTTPS API configured by Django.

Phone verification uses the configured SMS provider. If `SMS_PROVIDER` is unset, the app selects Twilio when its three credentials are configured, otherwise Fast2SMS when its API key is configured; without either provider it uses the non-delivering `console` backend. For production, explicitly set one provider. To use Fast2SMS, set:

```text
SMS_PROVIDER=fast2sms
FAST2SMS_API_KEY=<your Fast2SMS API key>
FAST2SMS_SENDER_ID=FSTSMS
```

The sender ID is optional if you want to use the provider default. Twilio is supported through its HTTPS API and the existing `requests` dependency; configure `SMS_PROVIDER=twilio`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and `TWILIO_PHONE_NUMBER`. The default `console` SMS provider intentionally does not deliver or log OTPs, so set up a real SMS provider before enabling phone verification for production users. Keep all provider credentials in environment variables; do not commit them.

To send a live test from an environment configured for Brevo:

```text
python manage.py send_test_email recipient@example.com
```

Apply database migrations when deploying:

```text
python manage.py migrate
```

---

# 🛒 Shopping Cart

Customers can:

- Add products to cart
- Remove products from cart
- Update product quantity
- View cart subtotal
- View discount amount
- View discount percentage
- View delivery charges
- View final payable amount

The checkout amount is calculated from the cart/order data instead of relying only on browser-side values.

---

# 🚚 Delivery Methods

NAGRI supports multiple delivery options.

### Standard Delivery

- Estimated delivery: 5–7 days
- Free delivery when eligible

### Express Delivery

- Estimated delivery: 2–3 days
- Additional delivery charge

### Overnight Delivery

- Fast delivery option
- Additional delivery charge

---

# 💳 Payment System

The project supports multiple payment methods.

## Online Payment

Supported payment options include:

- 💳 Credit / Debit Card
- 🏦 Net Banking
- 📱 UPI
- 👛 Digital Wallet

Online payments follow a secure payment flow.

```text
Checkout
    ↓
Select Payment Method
    ↓
Review Order
    ↓
Order Created (Payment Pending)
    ↓
Payment Gateway
    ↓
Payment Verification
    ↓
Payment Successful
    ↓
Order Successfully Placed