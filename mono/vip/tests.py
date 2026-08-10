from django.contrib.auth.models import User
from django.test import TestCase

from unittest.mock import patch

from .models import Category, Product, Order, ContactSubmission, Wallet, CoinTransaction
from . import views


class StorefrontFlowTests(TestCase):
	def setUp(self):
		self.original_razorpay_client = views.razorpay_client
		views.razorpay_client = None
		self.category = Category.objects.create(name='Test', slug='test')
		self.product = Product.objects.create(
			name='Test product',
			description='A test item',
			price='100.00',
			category=self.category,
			stock_quantity=5,
		)

	def tearDown(self):
		views.razorpay_client = self.original_razorpay_client

	def login(self):
		self.client.post('/register/', {
			'username': 'testuser',
			'email': 'test@example.com',
			'password1': 'SafeTestPassword123!',
			'password2': 'SafeTestPassword123!',
		})

	def test_public_pages_and_invalid_price_filter(self):
		for path in [
			'/', '/products/', '/about/', '/contact/', '/faq/',
			'/search/?q=test', f'/product/{self.product.pk}/',
			'/price-range/?min=bad&max=also-bad', '/payment-error/',
		]:
			with self.subTest(path=path):
				self.assertEqual(self.client.get(path).status_code, 200)

	def test_product_cards_link_to_each_product(self):
		second = Product.objects.create(
			name='Second product',
			description='Another item',
			price='200.00',
			category=self.category,
			stock_quantity=2,
		)
		response = self.client.get('/products/')
		self.assertContains(response, f'href="/product/{self.product.pk}/"')
		self.assertContains(response, f'href="/product/{second.pk}/"')
		self.assertContains(response, self.product.description)
		self.assertContains(response, second.description)

	def test_protected_and_state_changing_routes(self):
		self.assertEqual(self.client.get('/wishlist/').status_code, 302)
		self.login()
		self.assertEqual(
			self.client.post(f'/add-to-cart/{self.product.pk}/', {'quantity': 2}).status_code,
			302,
		)
		self.assertEqual(self.client.get('/cart/').status_code, 200)
		self.assertEqual(self.client.get('/logout/').status_code, 405)

	def test_cod_checkout_creates_one_order(self):
		self.login()
		self.client.post(f'/add-to-cart/{self.product.pk}/', {'quantity': 2})
		self.assertEqual(self.client.get('/checkout/').status_code, 200)
		self.assertEqual(Order.objects.count(), 0)
		response = self.client.post('/checkout/', {
			'payment_method': 'COD',
			'place_order': 'COD',
		})
		self.assertEqual(response.status_code, 200)
		self.assertEqual(Order.objects.count(), 1)

	def test_contact_submission_is_saved(self):
		response = self.client.post('/contact/', {
			'name': 'Test visitor',
			'email': 'visitor@example.com',
			'message': 'Please help.',
		})
		self.assertEqual(response.status_code, 302)
		self.assertTrue(ContactSubmission.objects.filter(email='visitor@example.com').exists())

	def test_wallet_coins_are_spent_once_for_cod_order(self):
		self.login()
		wallet = Wallet.objects.create(user=User.objects.get(username='testuser'), coins=50)
		self.client.post(f'/add-to-cart/{self.product.pk}/', {'quantity': 1})
		response = self.client.post('/checkout/', {
			'payment_method': 'COD',
			'place_order': 'COD',
			'coins_to_use': '20',
		})
		self.assertEqual(response.status_code, 200)
		wallet.refresh_from_db()
		self.assertGreaterEqual(wallet.coins, 30)
		self.assertLessEqual(wallet.coins, 130)
		self.assertEqual(CoinTransaction.objects.filter(wallet=wallet, transaction_type='SPENT').count(), 1)
		self.assertEqual(Order.objects.get().coins_used, 20)

	@patch('vip.views.razorpay_client')
	def test_razorpay_signature_marks_pending_order_paid(self, client):
		self.login()
		self.client.post(f'/add-to-cart/{self.product.pk}/', {'quantity': 1})
		client.order.create.return_value = {'id': 'order_test_123'}
		client.utility.verify_payment_signature.return_value = None
		self.client.get('/checkout/')
		order = Order.objects.get()
		response = self.client.post('/payment-success/', {
			'razorpay_payment_id': 'pay_test',
			'razorpay_order_id': order.razorpay_order_id,
			'razorpay_signature': 'signature_test',
		})
		self.assertEqual(response.status_code, 200)
		order.refresh_from_db()
		self.assertEqual(order.payment_status, 'Paid')
		self.assertEqual(order.status, 'Processing')
