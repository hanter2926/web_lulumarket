from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from urllib.parse import urlparse


class HomeSlider(models.Model):
    """
    Database model for homepage promotional sliders/advertisement banners.
    
    - Maximum 8 active sliders allowed
    - Minimum 3 recommended for display
    - Supports internal and external URLs
    - Mobile-responsive images
    - Ordered display system
    """
    
    title = models.CharField(
        max_length=200,
        help_text="Main promotional title (e.g., 'Summer Sale 2024')"
    )
    subtitle = models.CharField(
        max_length=300,
        blank=True,
        null=True,
        help_text="Secondary text/tagline (e.g., 'Up to 50% Off')"
    )
    image = models.ImageField(
        upload_to="sliders/",
        help_text="Desktop/main promotional image (recommended: 1200x400px)"
    )
    mobile_image = models.ImageField(
        upload_to="sliders/",
        blank=True,
        null=True,
        help_text="Optional mobile-optimized image (recommended: 600x400px)"
    )
    button_text = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Call-to-action button text (e.g., 'Shop Now')"
    )
    button_link = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Button destination URL (internal path or full URL)"
    )
    display_order = models.PositiveIntegerField(
        default=0,
        help_text="Display order on homepage (lower numbers show first)"
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Only active sliders appear on homepage"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['display_order', 'created_at']
        verbose_name = "Homepage Slider"
        verbose_name_plural = "Homepage Sliders"
        indexes = [
            models.Index(fields=['is_active', 'display_order']),
        ]
    
    def __str__(self):
        return f"{self.title} (Order: {self.display_order})"
    
    def clean(self):
        """Validate slider before saving."""
        errors = {}
        
        # Validate button_link if provided
        if self.button_link:
            self._validate_button_link(errors)
        
        # Check active slider limit if this slider is being activated
        if self.is_active and self.pk is None:  # New slider being created
            active_count = HomeSlider.objects.filter(is_active=True).count()
            if active_count >= 8:
                errors['is_active'] = 'Maximum 8 active sliders allowed. Deactivate an existing slider first.'
        elif self.is_active and self.pk is not None:  # Existing slider being reactivated
            active_count = HomeSlider.objects.filter(is_active=True).exclude(pk=self.pk).count()
            if active_count >= 8:
                errors['is_active'] = 'Maximum 8 active sliders allowed. Deactivate an existing slider first.'
        
        if errors:
            raise ValidationError(errors)
    
    def _validate_button_link(self, errors):
        """Validate the button_link field."""
        link = self.button_link.strip()
        
        # Skip validation if empty
        if not link:
            return
        
        # Check for unsafe protocols
        parsed = urlparse(link)
        unsafe_protocols = ['javascript', 'data', 'vbscript']
        
        if parsed.scheme and parsed.scheme.lower() in unsafe_protocols:
            errors['button_link'] = 'Unsafe URL protocol. Use http://, https://, or internal paths.'
            return
        
        # If it has a scheme (http/https), validate as URL
        if parsed.scheme:
            if parsed.scheme.lower() not in ['http', 'https']:
                errors['button_link'] = 'Only HTTP/HTTPS URLs are allowed for external links.'
                return
            
            # Basic HTTP/HTTPS URL validation
            validator = URLValidator()
            try:
                validator(link)
            except ValidationError:
                errors['button_link'] = 'Invalid URL format. Use a valid HTTP/HTTPS URL.'
        else:
            # Assume it's an internal path - basic validation
            if not link.startswith('/'):
                errors['button_link'] = 'Internal links must start with / (e.g., /products/ or /category/123/)'
    
    def save(self, *args, **kwargs):
        """Save slider with validation."""
        self.full_clean()
        super().save(*args, **kwargs)
    
    @classmethod
    def get_active_sliders(cls):
        """Get active sliders ordered by display_order."""
        return cls.objects.filter(is_active=True).order_by('display_order')
    
    @classmethod
    def can_create_active_slider(cls):
        """Check if new active slider can be created."""
        return cls.objects.filter(is_active=True).count() < 8
