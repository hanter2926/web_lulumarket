import random
from django.db import transaction
from django.core.mail import send_mail
from django.conf import settings
from .models import Wallet, CoinTransaction


def send_order_confirmation(user_email, order_id, amount):
    """Send a simple order confirmation email.

    Parameters:
    - user_email: recipient email address (string)
    - order_id: order identifier (int or string)
    - amount: numeric amount (Decimal/float/int) or string
    """
    subject = f'Order Confirmation - #{order_id} | Lulumarket'
    message = (
        f'Thank you for shopping with Lulumarket!\n\n'
        f'Your order #{order_id} of ₹{amount} has been successfully placed.'
    )

    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [user_email],
        fail_silently=True,
    )


def calculate_and_add_coins(user, order_amount):
    coins_to_add = 0

    if 50 <= order_amount <= 3000:
        coins_to_add = random.randint(1, 100)
    elif 3001 <= order_amount <= 10000:
        coins_to_add = random.randint(50, 500)

    if coins_to_add > 0:
        wallet, created = Wallet.objects.get_or_create(user=user)
        wallet.coins += coins_to_add
        wallet.save()

        CoinTransaction.objects.create(
            wallet=wallet,
            coins=coins_to_add,
            transaction_type='EARNED',
            description=f"Earned from purchase of Rs. {order_amount}"
        )
        
    return coins_to_add


# 2. Redeem Coins Function (Aapka Function)
def apply_coins_discount(user, order_total, coins_to_use):
    if coins_to_use < 0 or coins_to_use > order_total:
        return order_total
    try:
        wallet = user.wallet
    except Wallet.DoesNotExist:
        return order_total
    if wallet.coins < coins_to_use:
        return order_total
    return order_total - coins_to_use


def spend_coins_for_order(order):
    """Spend an order's coins exactly once while holding the wallet row lock."""
    if not order.coins_used:
        return
    with transaction.atomic():
        wallet = Wallet.objects.select_for_update().get(user=order.user)
        description = f'Order #{order.pk}'
        if CoinTransaction.objects.filter(
            wallet=wallet,
            transaction_type='SPENT',
            description=description,
        ).exists():
            return
        if wallet.coins < order.coins_used:
            raise ValueError('Insufficient wallet coins.')
        wallet.coins -= order.coins_used
        wallet.save(update_fields=['coins'])
        CoinTransaction.objects.create(
            wallet=wallet,
            coins=order.coins_used,
            transaction_type='SPENT',
            description=description,
        )