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

- User Registration and Login
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