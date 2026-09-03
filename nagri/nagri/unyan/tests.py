from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from .models import HomeSlider
from PIL import Image
import io

User = get_user_model()


class HomeSliderModelTests(TestCase):
    """Test HomeSlider model functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Create a simple test image
        self.test_image = self.create_test_image()
        self.owner = User.objects.create_user(
            username='owner',
            email='owner@test.com',
            password='testpass123',
            is_owner=True
        )
    
    @staticmethod
    def create_test_image():
        """Create a simple test image."""
        file = io.BytesIO()
        image = Image.new('RGB', size=(1200, 400), color=(0, 0, 0))
        image.save(file, 'PNG')
        file.seek(0)
        return SimpleUploadedFile(
            "test_image.png",
            file.getvalue(),
            content_type="image/png"
        )
    
    def test_create_slider(self):
        """Test creating a new slider."""
        slider = HomeSlider.objects.create(
            title='Test Slider',
            subtitle='Test Subtitle',
            image=self.test_image,
            button_text='Shop Now',
            button_link='/products/',
            display_order=1,
            is_active=True
        )
        self.assertEqual(slider.title, 'Test Slider')
        self.assertTrue(slider.is_active)
        self.assertEqual(HomeSlider.objects.count(), 1)
    
    def test_max_active_sliders_limit(self):
        """Test that maximum 8 active sliders are enforced."""
        # Create 8 active sliders
        for i in range(8):
            HomeSlider.objects.create(
                title=f'Slider {i+1}',
                image=self.create_test_image(),
                display_order=i,
                is_active=True
            )
        
        # Try to create a 9th active slider - should fail
        slider_9 = HomeSlider(
            title='Slider 9',
            image=self.create_test_image(),
            display_order=8,
            is_active=True
        )
        with self.assertRaises(ValidationError):
            slider_9.save()
    
    def test_can_create_inactive_slider_beyond_limit(self):
        """Test that inactive sliders can be created beyond limit."""
        # Create 8 active sliders
        for i in range(8):
            HomeSlider.objects.create(
                title=f'Slider {i+1}',
                image=self.create_test_image(),
                display_order=i,
                is_active=True
            )
        
        # Should be able to create an inactive slider
        slider_9 = HomeSlider.objects.create(
            title='Slider 9',
            image=self.create_test_image(),
            display_order=8,
            is_active=False
        )
        self.assertFalse(slider_9.is_active)
        self.assertEqual(HomeSlider.objects.count(), 9)
    
    def test_slider_ordering(self):
        """Test that sliders are ordered by display_order."""
        for i in [3, 1, 2]:
            HomeSlider.objects.create(
                title=f'Slider {i}',
                image=self.create_test_image(),
                display_order=i,
                is_active=True
            )
        
        ordered = list(HomeSlider.objects.all())
        self.assertEqual(ordered[0].display_order, 1)
        self.assertEqual(ordered[1].display_order, 2)
        self.assertEqual(ordered[2].display_order, 3)
    
    def test_get_active_sliders_method(self):
        """Test the get_active_sliders class method."""
        # Create 5 active and 3 inactive
        for i in range(5):
            HomeSlider.objects.create(
                title=f'Active {i+1}',
                image=self.create_test_image(),
                is_active=True,
                display_order=i
            )
        
        for i in range(3):
            HomeSlider.objects.create(
                title=f'Inactive {i+1}',
                image=self.create_test_image(),
                is_active=False,
                display_order=i+10
            )
        
        active = HomeSlider.get_active_sliders()
        self.assertEqual(active.count(), 5)
    
    def test_can_create_active_slider_method(self):
        """Test the can_create_active_slider class method."""
        # No sliders yet
        self.assertTrue(HomeSlider.can_create_active_slider())
        
        # Create 7 active sliders
        for i in range(7):
            HomeSlider.objects.create(
                title=f'Slider {i+1}',
                image=self.create_test_image(),
                is_active=True,
                display_order=i
            )
        
        self.assertTrue(HomeSlider.can_create_active_slider())
        
        # Create 8th
        HomeSlider.objects.create(
            title='Slider 8',
            image=self.create_test_image(),
            is_active=True,
            display_order=7
        )
        
        self.assertFalse(HomeSlider.can_create_active_slider())
    
    def test_invalid_button_link_unsafe_protocol(self):
        """Test that unsafe URL protocols are rejected."""
        slider = HomeSlider(
            title='Bad Slider',
            image=self.create_test_image(),
            button_link='javascript:alert("xss")',
            is_active=True
        )
        with self.assertRaises(ValidationError):
            slider.save()
    
    def test_valid_external_url(self):
        """Test that valid external URLs are accepted."""
        slider = HomeSlider.objects.create(
            title='External Link Slider',
            image=self.create_test_image(),
            button_link='https://example.com/sale',
            is_active=True
        )
        self.assertEqual(slider.button_link, 'https://example.com/sale')
    
    def test_valid_internal_path(self):
        """Test that internal paths are accepted."""
        slider = HomeSlider.objects.create(
            title='Internal Link Slider',
            image=self.create_test_image(),
            button_link='/products/?category=electronics',
            is_active=True
        )
        self.assertEqual(slider.button_link, '/products/?category=electronics')


class SliderViewPermissionTests(TestCase):
    """Test permission checks on slider management views."""
    
    def setUp(self):
        """Set up test users and client."""
        self.client = Client()
        self.test_image = HomeSliderModelTests.create_test_image()
        
        # Create test users
        self.owner = User.objects.create_user(
            username='owner',
            email='owner@test.com',
            password='testpass123',
            is_owner=True
        )
        
        self.customer = User.objects.create_user(
            username='customer',
            email='customer@test.com',
            password='testpass123',
            is_customer=True
        )
        
        self.seller = User.objects.create_user(
            username='seller',
            email='seller@test.com',
            password='testpass123',
            is_vendor=True
        )
        
        self.staff_user = User.objects.create_user(
            username='staff',
            email='staff@test.com',
            password='testpass123',
            is_staff=True
        )
    
    def test_customer_cannot_access_slider_list(self):
        """Test that customers cannot access slider list."""
        self.client.login(username='customer', password='testpass123')
        response = self.client.get(reverse('slider_list'))
        self.assertEqual(response.status_code, 403)
    
    def test_seller_cannot_access_slider_list(self):
        """Test that sellers cannot access slider list."""
        self.client.login(username='seller', password='testpass123')
        response = self.client.get(reverse('slider_list'))
        self.assertEqual(response.status_code, 403)
    
    def test_staff_cannot_access_slider_list(self):
        """Test that non-owner staff cannot access slider list."""
        self.client.login(username='staff', password='testpass123')
        response = self.client.get(reverse('slider_list'))
        self.assertEqual(response.status_code, 403)
    
    def test_owner_can_access_slider_list(self):
        """Test that owner can access slider list."""
        self.client.login(username='owner', password='testpass123')
        response = self.client.get(reverse('slider_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Homepage Sliders')
    
    def test_unauthenticated_redirects_to_login(self):
        """Test that unauthenticated users are redirected to login."""
        response = self.client.get(reverse('slider_list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)


class SliderCRUDTests(TestCase):
    """Test CRUD operations on sliders."""
    
    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.test_image = HomeSliderModelTests.create_test_image()
        
        self.owner = User.objects.create_user(
            username='owner',
            email='owner@test.com',
            password='testpass123',
            is_owner=True
        )
        self.client.login(username='owner', password='testpass123')
    
    def test_create_slider_view(self):
        """Test creating slider via POST."""
        response = self.client.post(reverse('slider_add'), {
            'title': 'Summer Sale',
            'subtitle': 'Up to 50% Off',
            'image': self.test_image,
            'button_text': 'Shop Now',
            'button_link': '/products/',
            'display_order': 1,
            'is_active': True
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(HomeSlider.objects.count(), 1)
        self.assertEqual(HomeSlider.objects.first().title, 'Summer Sale')
    
    def test_edit_slider_view(self):
        """Test editing an existing slider."""
        slider = HomeSlider.objects.create(
            title='Original Title',
            image=self.test_image,
            display_order=1,
            is_active=True
        )
        
        response = self.client.post(reverse('slider_edit', args=[slider.id]), {
            'title': 'Updated Title',
            'image': self.test_image,
            'display_order': 2,
            'is_active': True
        })
        
        slider.refresh_from_db()
        self.assertEqual(slider.title, 'Updated Title')
        self.assertEqual(slider.display_order, 2)
    
    def test_delete_slider_view(self):
        """Test deleting a slider."""
        slider = HomeSlider.objects.create(
            title='To Delete',
            image=self.test_image,
            is_active=True
        )
        slider_id = slider.id
        
        response = self.client.post(reverse('slider_delete', args=[slider_id]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(HomeSlider.objects.filter(id=slider_id).exists())
    
    def test_toggle_slider_status(self):
        """Test toggling slider active/inactive status."""
        slider = HomeSlider.objects.create(
            title='Toggle Test',
            image=self.test_image,
            is_active=True
        )
        
        response = self.client.post(reverse('slider_toggle', args=[slider.id]))
        slider.refresh_from_db()
        self.assertFalse(slider.is_active)
        
        response = self.client.post(reverse('slider_toggle', args=[slider.id]))
        slider.refresh_from_db()
        self.assertTrue(slider.is_active)


class HomepageSliderDisplayTests(TestCase):
    """Test slider display on homepage."""
    
    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.test_image = HomeSliderModelTests.create_test_image()
    
    def test_homepage_with_no_sliders(self):
        """Test homepage works when no sliders exist."""
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Welcome to Nagri')
    
    def test_homepage_with_active_sliders(self):
        """Test homepage displays active sliders."""
        slider = HomeSlider.objects.create(
            title='Test Promotion',
            subtitle='Limited Time',
            image=self.test_image,
            button_text='Shop',
            button_link='/products/',
            is_active=True,
            display_order=1
        )
        
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Promotion')
        self.assertContains(response, 'homeSlider')
    
    def test_homepage_only_shows_active_sliders(self):
        """Test that homepage only shows active sliders."""
        active = HomeSlider.objects.create(
            title='Active Promotion',
            image=self.test_image,
            is_active=True,
            display_order=1
        )
        
        inactive = HomeSlider.objects.create(
            title='Inactive Promotion',
            image=self.test_image,
            is_active=False,
            display_order=2
        )
        
        response = self.client.get(reverse('home'))
        self.assertContains(response, 'Active Promotion')
        self.assertNotContains(response, 'Inactive Promotion')
    
    def test_homepage_sliders_ordered_by_display_order(self):
        """Test that sliders are displayed in correct order."""
        slider2 = HomeSlider.objects.create(
            title='Second Slider',
            image=self.test_image,
            is_active=True,
            display_order=2
        )
        
        slider1 = HomeSlider.objects.create(
            title='First Slider',
            image=self.test_image,
            is_active=True,
            display_order=1
        )
        
        response = self.client.get(reverse('home'))
        content = response.content.decode()
        first_pos = content.find('First Slider')
        second_pos = content.find('Second Slider')
        self.assertLess(first_pos, second_pos)

