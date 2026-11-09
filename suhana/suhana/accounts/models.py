from django.db import models
from django.utils import timezone

class PendingSignup(models.Model):
    username = models.CharField(max_length=150)
    email = models.EmailField(unique=True)   
    password_hash = models.CharField(max_length=128)
    otp_hash = models.CharField(max_length=128)
    otp_expiry = models.DateTimeField()
    failed_attempts = models.PositiveIntegerField(default=0)
    last_otp_sent_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.email