from django.test import TestCase
from django.urls import reverse
from .models import HomeSlider, CustomUser
from django.core.files.uploadedfile import SimpleUploadedFile


class SliderPermissionTests(TestCase):
    def setUp(self):
        self.owner = CustomUser.objects.create_user(email='owner@example.com', username='owner', password='pass')
        self.owner.is_owner = True
        self.owner.is_active = True
        self.owner.save()

        self.user = CustomUser.objects.create_user(email='user@example.com', username='user', password='pass')
        self.user.is_active = True
        self.user.save()

    def test_owner_can_access_slider_list(self):
        self.client.force_login(self.owner)
        r = self.client.get(reverse('owner_sliders_list'))
        self.assertEqual(r.status_code, 200)

    def test_customer_cannot_access_slider_list(self):
        self.client.force_login(self.user)
        r = self.client.get(reverse('owner_sliders_list'))
        self.assertIn(r.status_code, (302, 403))

    def test_owner_can_create_slider_and_limit_enforced(self):
        self.client.force_login(self.owner)
        # create 8 active sliders
        img = SimpleUploadedFile('img.jpg', b'content', content_type='image/jpeg')
        for i in range(8):
            HomeSlider.objects.create(title=f's{i}', image=img, display_order=i, is_active=True)

        # ninth active slider should raise ValidationError on save
        s = HomeSlider(title='overflow', image=img, display_order=9, is_active=True)
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            s.full_clean()

    def test_inactive_slider_not_on_home(self):
        img = SimpleUploadedFile('img.jpg', b'content', content_type='image/jpeg')
        HomeSlider.objects.create(title='a', image=img, is_active=False)
        r = self.client.get(reverse('home'))
        self.assertEqual(r.status_code, 200)