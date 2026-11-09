from django.conf import settings
from django.db import models


class StoragePlan(models.Model):
    name = models.CharField(max_length=80, unique=True)
    quota_bytes = models.PositiveBigIntegerField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["quota_bytes"]

    def __str__(self):
        return self.name


class UserStorage(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    plan = models.ForeignKey(StoragePlan, on_delete=models.PROTECT)
    used_bytes = models.PositiveBigIntegerField(default=0)

    @property
    def available_bytes(self):
        return max(self.plan.quota_bytes - self.used_bytes, 0)

    def can_store(self, size_bytes):
        return size_bytes >= 0 and self.used_bytes + size_bytes <= self.plan.quota_bytes


class Folder(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="children"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "parent", "name"], name="unique_folder_per_owner_parent"
            )
        ]
        ordering = ["name"]

    def __str__(self):
        return self.name


class StoredFile(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    folder = models.ForeignKey(
        Folder, null=True, blank=True, on_delete=models.CASCADE, related_name="files"
    )
    name = models.CharField(max_length=255)
    file = models.FileField(upload_to="user-files/%Y/%m/")
    size_bytes = models.PositiveBigIntegerField()
    content_type = models.CharField(max_length=150, blank=True)
    sha256 = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "folder", "name"], name="unique_file_per_owner_folder"
            )
        ]
        ordering = ["-updated_at"]

    def __str__(self):
        return self.name
