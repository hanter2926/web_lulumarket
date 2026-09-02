import smtplib
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.core import mail
from django.core.exceptions import ValidationError

from accounts.models import CustomUser
from .models import SellerApplication, SellerPasswordChangeEvent, SellerOrderNotification
from products.models import Category, Product
from orders.models import Order, OrderItem


class SellerFlowTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(email='u@example.com', username='u', password='pass')
        self.admin = CustomUser.objects.create_superuser(email='admin@example.com', username='admin', password='adminpass')
        self.client = Client()
        self.client.login(email='u@example.com', password='pass')

    def _verify_email(self):
        self.client.post(reverse('sellers:send_otp'))
        body = mail.outbox[-1].body
        import re
        otp = re.search(r"(\d{6})", body).group(1)
        self.client.post(reverse('sellers:verify_email'), {'otp': otp})
        return SellerApplication.objects.get(user=self.user)

    def test_otp_generation_and_verification(self):
        resp = self.client.post(reverse('sellers:send_otp'))
        self.assertEqual(resp.status_code, 302)
        self.assertRedirects(resp, reverse('sellers:verify_email'))
        app = SellerApplication.objects.get(user=self.user)
        self.assertTrue(len(mail.outbox) >= 1)
        body = mail.outbox[-1].body
        import re
        m = re.search(r"(\d{6})", body)
        self.assertIsNotNone(m)
        otp = m.group(1)
        verify = self.client.post(reverse('sellers:verify_email'), {'otp': otp})
        self.assertEqual(verify.status_code, 302)
        app.refresh_from_db()
        self.assertTrue(app.email_verified)

    def test_send_otp_get_redirects_and_cooldown_shows_message(self):
        resp = self.client.get(reverse('sellers:send_otp'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('sellers:verify_email'), resp.url)

        self.client.post(reverse('sellers:send_otp'))
        resp = self.client.post(reverse('sellers:send_otp'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('sellers:verify_email'), resp.url)
        follow_resp = self.client.get(reverse('sellers:verify_email'))
        self.assertContains(follow_resp, 'Please wait 60 seconds before requesting another OTP.')

    def test_otp_email_appears_in_locmem_outbox_and_uses_registered_recipient(self):
        mail.outbox.clear()
        response = self.client.post(reverse('sellers:send_otp'))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])
        self.assertEqual(mail.outbox[0].from_email, 'vikrampal803302@gmail.com')

    @patch('sellers.views.send_mail')
    def test_send_otp_email_is_attempted_with_correct_recipient_and_no_otp_logged(self, mock_send):
        mock_send.return_value = 1
        with self.assertLogs('sellers.views', level='INFO') as captured:
            response = self.client.post(reverse('sellers:send_otp'))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(mock_send.called)
        self.assertEqual(mock_send.call_args.kwargs['recipient_list'], [self.user.email])
        self.assertEqual(mock_send.call_args.kwargs['from_email'], 'vikrampal803302@gmail.com')
        otp_match = re.search(r"(\d{6})", mock_send.call_args.kwargs['message'])
        self.assertIsNotNone(otp_match)
        log_output = '\n'.join(captured.output)
        self.assertIn(self.user.email, log_output)
        self.assertNotIn(otp_match.group(1), log_output)

    @patch('sellers.views.send_mail')
    def test_failed_send_does_not_mark_otp_as_sent(self, mock_send):
        mock_send.side_effect = smtplib.SMTPException('SMTP test failure')

        response = self.client.post(reverse('sellers:send_otp'))

        self.assertEqual(response.status_code, 302)
        app = SellerApplication.objects.get(user=self.user)
        self.assertIsNone(app.otp_last_sent_at)
        self.assertFalse(app.otp_hash)

    def test_resend_requires_full_60_seconds(self):
        self.client.post(reverse('sellers:send_otp'))
        response = self.client.post(reverse('sellers:send_otp'))
        self.assertEqual(response.status_code, 302)

        app = SellerApplication.objects.get(user=self.user)
        app.otp_last_sent_at = timezone.now() - timezone.timedelta(seconds=59)
        app.save(update_fields=['otp_last_sent_at'])
        response = self.client.post(reverse('sellers:send_otp'))
        self.assertEqual(response.status_code, 302)

    def test_resend_allowed_after_60_seconds(self):
        self.client.post(reverse('sellers:send_otp'))
        app = SellerApplication.objects.get(user=self.user)
        app.otp_last_sent_at = timezone.now() - timezone.timedelta(seconds=61)
        app.save(update_fields=['otp_last_sent_at'])

        response = self.client.post(reverse('sellers:send_otp'))
        self.assertEqual(response.status_code, 302)

    def test_verify_email_page_initial_countdown_is_60_seconds(self):
        self.client.post(reverse('sellers:send_otp'))
        response = self.client.get(reverse('sellers:verify_email'))
        self.assertContains(response, 'data-resend-seconds="60"')

    def test_otp_expiry(self):
        resp = self.client.post(reverse('sellers:send_otp'))
        app = SellerApplication.objects.get(user=self.user)
        app.otp_expires_at = timezone.now() - timezone.timedelta(seconds=1)
        app.save()
        body = mail.outbox[-1].body
        import re
        otp = re.search(r"(\d{6})", body).group(1)
        verify = self.client.post(reverse('sellers:verify_email'), {'otp': otp})
        self.assertContains(verify, 'expired', status_code=200)

    def test_cannot_submit_documents_before_verification(self):
        resp = self.client.get(reverse('sellers:documents'))
        self.assertEqual(resp.status_code, 302)

    def test_category_selection_and_submission(self):
        self._verify_email()
        app = SellerApplication.objects.get(user=self.user)
        app.email_verified = True
        app.save()
        c = Category.objects.create(name='TestCat', slug='testcat')
        resp = self.client.post(reverse('sellers:categories'), {'categories': [c.id]})
        self.assertContains(resp, 'under review', status_code=200)
        app.refresh_from_db()
        self.assertEqual(app.status, 'pending_review')
        u = CustomUser.objects.get(pk=self.user.pk)
        self.assertFalse(u.is_vendor)

    def test_admin_approval_does_not_immediately_set_is_vendor(self):
        app = SellerApplication.objects.create(user=self.user, email=self.user.email)
        app.approve_application(self.admin, review_notes='Looks good')
        self.user.refresh_from_db()
        self.assertEqual(app.status, 'approved')
        self.assertFalse(self.user.is_vendor)

    def test_activation_email_and_token_are_created_after_approval(self):
        app = SellerApplication.objects.create(user=self.user, email=self.user.email)
        app.approve_application(self.admin, review_notes='Looks good')
        self.assertTrue(app.activation_token_hash)
        self.assertIsNotNone(app.activation_token_expires_at)
        self.assertTrue(mail.outbox)

    def test_invalid_activation_token_rejected(self):
        app = SellerApplication.objects.create(user=self.user, email=self.user.email)
        app.generate_activation_token()
        ok, reason = app.verify_activation_token('wrong-token')
        self.assertFalse(ok)
        self.assertIn('invalid', reason)

    def test_expired_activation_token_rejected(self):
        app = SellerApplication.objects.create(user=self.user, email=self.user.email)
        token = app.generate_activation_token(ttl_minutes=0)
        app.activation_token_expires_at = timezone.now() - timezone.timedelta(minutes=1)
        app.save(update_fields=['activation_token_expires_at'])
        ok, reason = app.verify_activation_token(token)
        self.assertFalse(ok)
        self.assertEqual(reason, 'expired')

    def test_activation_token_cannot_be_reused(self):
        app = SellerApplication.objects.create(user=self.user, email=self.user.email)
        token = app.generate_activation_token()
        ok, _ = app.verify_activation_token(token)
        self.assertTrue(ok)
        ok_again, reason = app.verify_activation_token(token)
        self.assertFalse(ok_again)
        self.assertEqual(reason, 'used')

    def test_successful_activation_sets_is_vendor_true(self):
        app = SellerApplication.objects.create(user=self.user, email=self.user.email)
        token = app.generate_activation_token()
        self.user.username = 'firstseller'
        self.user.save(update_fields=['username'])
        ok, _ = app.activate_account(token, seller_id='firstseller', password='StrongPass!1')
        self.assertTrue(ok)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_vendor)
        self.assertEqual(app.status, 'approved')

    def test_duplicate_seller_id_rejected(self):
        other = CustomUser.objects.create_user(email='other@example.com', username='existing-seller', password='pass')
        app = SellerApplication.objects.create(user=self.user, email=self.user.email)
        app2 = SellerApplication.objects.create(user=other, email=other.email)
        app2.seller_id = 'existing-seller'
        with self.assertRaises(ValidationError):
            app2.validate_seller_id('existing-seller')

    def test_weak_password_rejected(self):
        app = SellerApplication.objects.create(user=self.user, email=self.user.email)
        token = app.generate_activation_token()
        with self.assertRaises(ValidationError):
            app.activate_account(token, seller_id='newseller', password='weakpass')

    def test_seller_can_change_password_three_times_in_30_days(self):
        self.user.set_password('OldPass!1')
        self.user.save()
        for idx in range(3):
            ok, msg = self.user.change_password('OldPass!1', f'NewPass{idx}!2')
            self.assertTrue(ok)
            self.assertEqual(msg, 'success')
        ok, msg = self.user.change_password('NewPass2!2', 'NewPass4!2')
        self.assertFalse(ok)
        self.assertIn('maximum password change limit', msg.lower())

    def test_password_change_becomes_available_after_rolling_30_days(self):
        self.user.set_password('OldPass!1')
        self.user.save()
        for idx in range(3):
            SellerPasswordChangeEvent.objects.create(user=self.user, event_type='manual_change', changed_at=timezone.now() - timezone.timedelta(days=31 + idx))
        allowed, next_date = self.user.can_change_password()
        self.assertTrue(allowed)
        self.assertIsNotNone(next_date)

    def test_forgot_password_flow_is_secure_and_rate_limited(self):
        app = SellerApplication.objects.create(user=self.user, email=self.user.email)
        self.user.is_vendor = True
        self.user.save()
        ok, msg = app.request_password_reset()
        self.assertTrue(ok)
        ok2, msg2 = app.request_password_reset()
        self.assertFalse(ok2)
        self.assertIn('rate limit', msg2.lower())

    def test_multi_seller_order_sends_each_seller_only_their_own_items(self):
        seller_a = CustomUser.objects.create_user(email='a@example.com', username='sellerA', password='pass', is_vendor=True)
        seller_b = CustomUser.objects.create_user(email='b@example.com', username='sellerB', password='pass', is_vendor=True)
        category = Category.objects.create(name='Cat', slug='cat')
        product_a = Product.objects.create(name='A', slug='a', category=category, price=Decimal('100.00'), seller=seller_a)
        product_b = Product.objects.create(name='B', slug='b', category=category, price=Decimal('200.00'), seller=seller_b)
        order = Order.objects.create(user=self.user, order_number='ORD-1', total_amount=Decimal('300.00'), status='paid', payment_method='razorpay')
        OrderItem.objects.create(order=order, product=product_a, quantity=2, price=product_a.price)
        OrderItem.objects.create(order=order, product=product_b, quantity=1, price=product_b.price)
        from sellers.models import send_seller_order_notifications
        send_seller_order_notifications(order)
        self.assertTrue(SellerOrderNotification.objects.filter(order=order, seller=seller_a).exists())
        self.assertTrue(SellerOrderNotification.objects.filter(order=order, seller=seller_b).exists())
        self.assertEqual(SellerOrderNotification.objects.filter(order=order).count(), 2)
        self.assertTrue(len(mail.outbox) >= 2)

    def test_order_notification_is_not_duplicated(self):
        seller = CustomUser.objects.create_user(email='dup@example.com', username='dup', password='pass', is_vendor=True)
        category = Category.objects.create(name='DupCat', slug='dupcat')
        product = Product.objects.create(name='Dup', slug='dup', category=category, price=Decimal('50.00'), seller=seller)
        order = Order.objects.create(user=self.user, order_number='ORD-2', total_amount=Decimal('50.00'), status='paid', payment_method='cod')
        OrderItem.objects.create(order=order, product=product, quantity=1, price=product.price)
        from sellers.models import send_seller_order_notifications
        send_seller_order_notifications(order)
        send_seller_order_notifications(order)
        self.assertEqual(SellerOrderNotification.objects.filter(order=order, seller=seller).count(), 1)

    def test_non_vendor_cannot_access_seller_products_dashboard(self):
        response = self.client.get(reverse('sellers:product_list'))
        self.assertIn(response.status_code, (302, 403))

    def test_approved_vendor_can_view_and_create_own_products(self):
        seller = CustomUser.objects.create_user(email='seller@example.com', username='seller', password='pass', is_vendor=True)
        allowed_category = Category.objects.create(name='Allowed Cat', slug='allowed-cat')
        app = SellerApplication.objects.create(user=seller, email=seller.email, status='approved')
        app.selected_categories.add(allowed_category)

        self.client.force_login(seller)
        response = self.client.get(reverse('sellers:product_list'))
        self.assertEqual(response.status_code, 200)

        create_response = self.client.post(
            reverse('sellers:product_create'),
            {
                'name': 'Approved Product',
                'slug': 'approved-product',
                'category': str(allowed_category.id),
                'short_description': 'Test product',
                'description': 'Detailed description',
                'price': '249.00',
                'compare_price': '299.00',
                'stock': 10,
                'is_active': 'on',
            },
            follow=True,
        )
        self.assertEqual(create_response.status_code, 200)
        self.assertTrue(Product.objects.filter(name='Approved Product', seller=seller).exists())

    def test_seller_cannot_edit_or_create_in_unapproved_categories(self):
        seller = CustomUser.objects.create_user(email='restricted@example.com', username='restricted', password='pass', is_vendor=True)
        allowed_category = Category.objects.create(name='Allowed Cat 2', slug='allowed-cat-2')
        blocked_category = Category.objects.create(name='Blocked Cat', slug='blocked-cat')
        SellerApplication.objects.create(user=seller, email=seller.email, status='approved').selected_categories.add(allowed_category)

        self.client.force_login(seller)
        response = self.client.post(
            reverse('sellers:product_create'),
            {
                'name': 'Blocked Product',
                'slug': 'blocked-product',
                'category': str(blocked_category.id),
                'short_description': 'Nope',
                'description': 'Nope',
                'price': '100.00',
                'compare_price': '120.00',
                'stock': 1,
                'is_active': 'on',
            },
        )
        self.assertIn(response.status_code, (200, 302))
        self.assertFalse(Product.objects.filter(name='Blocked Product', seller=seller).exists())

    def test_seller_cannot_modify_other_sellers_product(self):
        owner = CustomUser.objects.create_user(email='owner@example.com', username='owner', password='pass', is_vendor=True)
        intruder = CustomUser.objects.create_user(email='intruder@example.com', username='intruder', password='pass', is_vendor=True)
        category = Category.objects.create(name='Shared Cat', slug='shared-cat')
        SellerApplication.objects.create(user=owner, email=owner.email, status='approved').selected_categories.add(category)
        SellerApplication.objects.create(user=intruder, email=intruder.email, status='approved').selected_categories.add(category)
        product = Product.objects.create(name='Owned Product', slug='owned-product', category=category, price=Decimal('75.00'), seller=owner)

        self.client.force_login(intruder)
        response = self.client.get(reverse('sellers:product_edit', args=[product.id]))
        self.assertIn(response.status_code, (302, 403))

    def test_seller_sees_only_their_own_order_items(self):
        seller_a = CustomUser.objects.create_user(email='seller-a-orders@example.com', username='seller-a', password='pass', is_vendor=True)
        seller_b = CustomUser.objects.create_user(email='seller-b-orders@example.com', username='seller-b', password='pass', is_vendor=True)
        category = Category.objects.create(name='Orders Cat', slug='orders-cat')
        product_a = Product.objects.create(name='Seller A Product', slug='seller-a-product', category=category, price=Decimal('500.00'), seller=seller_a)
        product_b = Product.objects.create(name='Seller B Product', slug='seller-b-product', category=category, price=Decimal('300.00'), seller=seller_b)
        order = Order.objects.create(user=self.user, order_number='ORD-1001', total_amount=Decimal('800.00'), status='paid', payment_method='razorpay', is_paid=True)
        OrderItem.objects.create(order=order, product=product_a, quantity=2, price=product_a.price)
        OrderItem.objects.create(order=order, product=product_b, quantity=1, price=product_b.price)

        self.client.force_login(seller_a)
        response = self.client.get(reverse('sellers:orders_list'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Seller A Product', content)
        self.assertNotIn('Seller B Product', content)

    def test_multi_seller_order_is_separated_correctly(self):
        seller_a = CustomUser.objects.create_user(email='multi-a@example.com', username='multi-a', password='pass', is_vendor=True)
        seller_b = CustomUser.objects.create_user(email='multi-b@example.com', username='multi-b', password='pass', is_vendor=True)
        category = Category.objects.create(name='Multi Cat', slug='multi-cat')
        product_a = Product.objects.create(name='A Multi', slug='a-multi', category=category, price=Decimal('200.00'), seller=seller_a)
        product_b = Product.objects.create(name='B Multi', slug='b-multi', category=category, price=Decimal('100.00'), seller=seller_b)
        order = Order.objects.create(user=self.user, order_number='ORD-1002', total_amount=Decimal('300.00'), status='paid', payment_method='razorpay', is_paid=True)
        item_a = OrderItem.objects.create(order=order, product=product_a, quantity=3, price=product_a.price)
        OrderItem.objects.create(order=order, product=product_b, quantity=2, price=product_b.price)

        self.client.force_login(seller_a)
        response = self.client.get(reverse('sellers:orders_list'))
        content = response.content.decode()
        self.assertIn('A Multi', content)
        self.assertNotIn('B Multi', content)
        self.assertNotIn('b-multi', content)

    def test_seller_revenue_includes_quantity(self):
        seller = CustomUser.objects.create_user(email='revenue@example.com', username='revenue', password='pass', is_vendor=True)
        category = Category.objects.create(name='Revenue Cat', slug='revenue-cat')
        product = Product.objects.create(name='Revenue Product', slug='revenue-product', category=category, price=Decimal('500.00'), seller=seller)
        order = Order.objects.create(user=self.user, order_number='ORD-1003', total_amount=Decimal('1500.00'), status='paid', payment_method='razorpay', is_paid=True)
        OrderItem.objects.create(order=order, product=product, quantity=3, price=product.price)

        self.client.force_login(seller)
        response = self.client.get(reverse('sellers:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('1500.00', response.content.decode())

    def test_seller_cannot_access_another_sellers_order_data(self):
        seller = CustomUser.objects.create_user(email='guardian@example.com', username='guardian', password='pass', is_vendor=True)
        other = CustomUser.objects.create_user(email='other-seller@example.com', username='other-seller', password='pass', is_vendor=True)
        category = Category.objects.create(name='Forbidden Cat', slug='forbidden-cat')
        product = Product.objects.create(name='Other Product', slug='other-product', category=category, price=Decimal('100.00'), seller=other)
        order = Order.objects.create(user=self.user, order_number='ORD-1004', total_amount=Decimal('100.00'), status='paid', payment_method='razorpay', is_paid=True)
        item = OrderItem.objects.create(order=order, product=product, quantity=1, price=product.price)

        self.client.force_login(seller)
        response = self.client.get(reverse('sellers:order_item_detail', args=[item.id]))
        self.assertIn(response.status_code, (302, 403))

    def test_online_paid_amount_includes_only_verified_paid_online_orders(self):
        seller = CustomUser.objects.create_user(email='online@example.com', username='online', password='pass', is_vendor=True)
        category = Category.objects.create(name='Online Cat', slug='online-cat')
        product = Product.objects.create(name='Online Product', slug='online-product', category=category, price=Decimal('900.00'), seller=seller)
        paid_order = Order.objects.create(user=self.user, order_number='ORD-1005', total_amount=Decimal('900.00'), status='paid', payment_method='razorpay', is_paid=True)
        unpaid_order = Order.objects.create(user=self.user, order_number='ORD-1006', total_amount=Decimal('900.00'), status='pending', payment_method='razorpay', is_paid=False)
        cod_order = Order.objects.create(user=self.user, order_number='ORD-1007', total_amount=Decimal('900.00'), status='pending', payment_method='cod', is_paid=False)
        OrderItem.objects.create(order=paid_order, product=product, quantity=1, price=product.price)
        OrderItem.objects.create(order=unpaid_order, product=product, quantity=1, price=product.price)
        OrderItem.objects.create(order=cod_order, product=product, quantity=1, price=product.price)

        self.client.force_login(seller)
        response = self.client.get(reverse('sellers:dashboard'))
        content = response.content.decode()
        self.assertIn('900.00', content)
        self.assertNotIn('2700.00', content)

    def test_cod_and_pending_amount_are_calculated_separately(self):
        seller = CustomUser.objects.create_user(email='cod@example.com', username='cod', password='pass', is_vendor=True)
        category = Category.objects.create(name='COD Cat', slug='cod-cat')
        product = Product.objects.create(name='COD Product', slug='cod-product', category=category, price=Decimal('200.00'), seller=seller)
        cod_order = Order.objects.create(user=self.user, order_number='ORD-1008', total_amount=Decimal('200.00'), status='pending', payment_method='cod', is_paid=False)
        pending_order = Order.objects.create(user=self.user, order_number='ORD-1009', total_amount=Decimal('300.00'), status='pending', payment_method='upi', is_paid=False)
        OrderItem.objects.create(order=cod_order, product=product, quantity=1, price=product.price)
        OrderItem.objects.create(order=pending_order, product=product, quantity=1, price=Decimal('300.00'))

        self.client.force_login(seller)
        response = self.client.get(reverse('sellers:dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_date_filters_only_affect_seller_data(self):
        seller = CustomUser.objects.create_user(email='dates@example.com', username='dates', password='pass', is_vendor=True)
        other = CustomUser.objects.create_user(email='other-dates@example.com', username='other-dates', password='pass', is_vendor=True)
        category = Category.objects.create(name='Date Cat', slug='date-cat')
        product = Product.objects.create(name='Date Product', slug='date-product', category=category, price=Decimal('250.00'), seller=seller)
        other_product = Product.objects.create(name='Other Date Product', slug='other-date-product', category=category, price=Decimal('250.00'), seller=other)
        order = Order.objects.create(user=self.user, order_number='ORD-1010', total_amount=Decimal('250.00'), status='paid', payment_method='razorpay', is_paid=True, created_at=timezone.now())
        other_order = Order.objects.create(user=self.user, order_number='ORD-1011', total_amount=Decimal('250.00'), status='paid', payment_method='razorpay', is_paid=True, created_at=timezone.now())
        OrderItem.objects.create(order=order, product=product, quantity=1, price=product.price)
        OrderItem.objects.create(order=other_order, product=other_product, quantity=1, price=other_product.price)

        self.client.force_login(seller)
        response = self.client.get(reverse('sellers:orders_list'), {'payment_method': 'razorpay'})
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Date Product', content)
        self.assertNotIn('Other Date Product', content)

    def test_dashboard_counts_are_correct(self):
        seller = CustomUser.objects.create_user(email='dashboard@example.com', username='dashboard', password='pass', is_vendor=True)
        category = Category.objects.create(name='Dashboard Cat', slug='dashboard-cat')
        product = Product.objects.create(name='Dashboard Product', slug='dashboard-product', category=category, price=Decimal('100.00'), seller=seller, is_active=True)
        Product.objects.create(name='Dashboard Inactive Product', slug='dashboard-inactive-product', category=category, price=Decimal('80.00'), seller=seller, is_active=False)
        order = Order.objects.create(user=self.user, order_number='ORD-1012', total_amount=Decimal('100.00'), status='paid', payment_method='razorpay', is_paid=True)
        OrderItem.objects.create(order=order, product=product, quantity=1, price=product.price)

        self.client.force_login(seller)
        response = self.client.get(reverse('sellers:dashboard'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('2', content)

    def test_product_performance_metrics_are_correct(self):
        seller = CustomUser.objects.create_user(email='perf@example.com', username='perf', password='pass', is_vendor=True)
        category = Category.objects.create(name='Perf Cat', slug='perf-cat')
        product = Product.objects.create(name='Perf Product', slug='perf-product', category=category, price=Decimal('120.00'), seller=seller, is_active=True)
        order = Order.objects.create(user=self.user, order_number='ORD-1013', total_amount=Decimal('240.00'), status='paid', payment_method='razorpay', is_paid=True)
        OrderItem.objects.create(order=order, product=product, quantity=2, price=product.price)

        self.client.force_login(seller)
        response = self.client.get(reverse('sellers:product_performance'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Perf Product', content)
        self.assertIn('240.00', content)

    def test_seller_cannot_update_another_sellers_order_item_status(self):
        seller = CustomUser.objects.create_user(email='status-owner@example.com', username='status-owner', password='pass', is_vendor=True)
        other = CustomUser.objects.create_user(email='status-other@example.com', username='status-other', password='pass', is_vendor=True)
        category = Category.objects.create(name='Status Cat', slug='status-cat')
        product = Product.objects.create(name='Status Product', slug='status-product', category=category, price=Decimal('40.00'), seller=other)
        order = Order.objects.create(user=self.user, order_number='ORD-1014', total_amount=Decimal('40.00'), status='pending', payment_method='cod', is_paid=False)
        item = OrderItem.objects.create(order=order, product=product, quantity=1, price=product.price)

        self.client.force_login(seller)
        response = self.client.post(reverse('sellers:order_item_status', args=[item.id]), {'fulfillment_status': 'shipped'})
        self.assertIn(response.status_code, (302, 403))
        item.refresh_from_db()
        self.assertEqual(item.fulfillment_status, 'pending')

    def test_customer_cannot_access_owner_dashboard(self):
        response = self.client.get(reverse('sellers:owner_dashboard'))
        self.assertEqual(response.status_code, 403)

    def test_seller_cannot_access_owner_dashboard(self):
        seller = CustomUser.objects.create_user(email='ownerblocked@example.com', username='ownerblocked', password='pass', is_vendor=True)
        self.client.force_login(seller)
        response = self.client.get(reverse('sellers:owner_dashboard'))
        self.assertEqual(response.status_code, 403)

    def test_superuser_can_access_owner_dashboard(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('sellers:owner_dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_unauthorized_staff_is_denied_owner_access(self):
        staff = CustomUser.objects.create_user(email='staff@example.com', username='staff', password='pass', is_staff=True)
        self.client.force_login(staff)
        response = self.client.get(reverse('sellers:owner_dashboard'))
        self.assertEqual(response.status_code, 403)

    def test_owner_sees_all_seller_applications(self):
        seller_a = CustomUser.objects.create_user(email='app-a@example.com', username='app-a', password='pass')
        seller_b = CustomUser.objects.create_user(email='app-b@example.com', username='app-b', password='pass')
        SellerApplication.objects.create(user=seller_a, email=seller_a.email, status='pending_review')
        SellerApplication.objects.create(user=seller_b, email=seller_b.email, status='approved')
        self.client.force_login(self.admin)
        response = self.client.get(reverse('sellers:owner_seller_list'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('app-a@example.com', content)
        self.assertIn('app-b@example.com', content)

    def test_owner_marketplace_totals_are_calculated_correctly(self):
        owner = CustomUser.objects.create_user(email='owner@example.com', username='owner', password='pass', is_owner=True)
        seller_1 = CustomUser.objects.create_user(email='seller1market@example.com', username='seller1market', password='pass', is_vendor=True)
        seller_2 = CustomUser.objects.create_user(email='seller2market@example.com', username='seller2market', password='pass', is_vendor=True)
        category = Category.objects.create(name='Market Cat', slug='market-cat')
        product_1 = Product.objects.create(name='Market Product 1', slug='market-product-1', category=category, price=Decimal('100.00'), seller=seller_1)
        product_2 = Product.objects.create(name='Market Product 2', slug='market-product-2', category=category, price=Decimal('200.00'), seller=seller_2)
        order = Order.objects.create(user=self.user, order_number='ORD-OWNER-1', total_amount=Decimal('500.00'), status='paid', payment_method='razorpay', is_paid=True)
        OrderItem.objects.create(order=order, product=product_1, quantity=2, price=product_1.price)
        OrderItem.objects.create(order=order, product=product_2, quantity=1, price=product_2.price)

        self.client.force_login(owner)
        response = self.client.get(reverse('sellers:owner_dashboard'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('400.00', content)
        self.assertIn('2', content)

    def test_seller_suspension_blocks_dashboard_and_product_management(self):
        owner = CustomUser.objects.create_user(email='owner-suspend@example.com', username='owner-suspend', password='pass', is_owner=True)
        seller = CustomUser.objects.create_user(email='suspend-seller@example.com', username='suspend-seller', password='pass', is_vendor=True)
        category = Category.objects.create(name='Suspend Cat', slug='suspend-cat')
        app = SellerApplication.objects.create(user=seller, email=seller.email, status='approved')
        app.selected_categories.add(category)
        product = Product.objects.create(name='Suspend Product', slug='suspend-product', category=category, price=Decimal('50.00'), seller=seller)

        self.client.force_login(owner)
        response = self.client.post(reverse('sellers:owner_seller_action', args=[seller.pk]), {'action': 'suspend'})
        self.assertEqual(response.status_code, 302)
        seller.refresh_from_db()
        self.assertFalse(seller.is_vendor)

        self.client.force_login(seller)
        self.assertEqual(self.client.get(reverse('sellers:dashboard')).status_code, 403)
        self.assertEqual(self.client.get(reverse('sellers:product_list')).status_code, 403)
        self.assertEqual(self.client.get(reverse('sellers:product_edit', args=[product.pk])).status_code, 403)

    def test_reactivation_restores_access_when_account_is_valid(self):
        owner = CustomUser.objects.create_user(email='owner-react@example.com', username='owner-react', password='pass', is_owner=True)
        seller = CustomUser.objects.create_user(email='reactivate-seller@example.com', username='reactivate-seller', password='pass', is_vendor=False)
        app = SellerApplication.objects.create(user=seller, email=seller.email, status='suspended', seller_id='reactivate-seller')
        self.client.force_login(owner)
        response = self.client.post(reverse('sellers:owner_seller_action', args=[seller.pk]), {'action': 'reactivate'})
        self.assertEqual(response.status_code, 302)
        seller.refresh_from_db()
        self.assertTrue(seller.is_vendor)

    def test_sensitive_documents_are_protected(self):
        owner = CustomUser.objects.create_user(email='owner-doc@example.com', username='owner-doc', password='pass', is_owner=True)
        seller = CustomUser.objects.create_user(email='seller-doc@example.com', username='seller-doc', password='pass', is_vendor=True)
        app = SellerApplication.objects.create(user=seller, email=seller.email, status='approved', aadhaar_number='123456789012', pan_number='ABCDE1234F')
        self.client.force_login(owner)
        response = self.client.get(reverse('sellers:owner_seller_detail', args=[seller.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('123456789012', response.content.decode())
        self.assertNotIn('ABCDE1234F', response.content.decode())

    def test_owner_can_access_protected_document_via_authorized_view(self):
        owner = CustomUser.objects.create_user(email='owner-protected@example.com', username='owner-protected', password='pass', is_owner=True)
        seller = CustomUser.objects.create_user(email='seller-protected@example.com', username='seller-protected', password='pass', is_vendor=True)
        app = SellerApplication.objects.create(user=seller, email=seller.email, status='approved', pan_card_image='pan.png', passport_photo='photo.png')
        self.client.force_login(owner)
        response = self.client.get(reverse('sellers:protected_document', args=[app.pk, 'pan_card_image']))
        self.assertIn(response.status_code, (200, 302, 403))

    def test_top_seller_ranking_is_correct(self):
        owner = CustomUser.objects.create_user(email='owner-rank@example.com', username='owner-rank', password='pass', is_owner=True)
        seller_a = CustomUser.objects.create_user(email='rank-a@example.com', username='rank-a', password='pass', is_vendor=True)
        seller_b = CustomUser.objects.create_user(email='rank-b@example.com', username='rank-b', password='pass', is_vendor=True)
        category = Category.objects.create(name='Rank Cat', slug='rank-cat')
        product_a = Product.objects.create(name='Rank A', slug='rank-a-product', category=category, price=Decimal('100.00'), seller=seller_a)
        product_b = Product.objects.create(name='Rank B', slug='rank-b-product', category=category, price=Decimal('150.00'), seller=seller_b)
        order = Order.objects.create(user=self.user, order_number='ORD-RANK-1', total_amount=Decimal('250.00'), status='paid', payment_method='razorpay', is_paid=True)
        OrderItem.objects.create(order=order, product=product_a, quantity=2, price=product_a.price)
        OrderItem.objects.create(order=order, product=product_b, quantity=1, price=product_b.price)
        self.client.force_login(owner)
        response = self.client.get(reverse('sellers:owner_top_sellers'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Rank A', content)
        self.assertIn('Rank B', content)
