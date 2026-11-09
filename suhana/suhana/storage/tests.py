from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase

from .models import StoragePlan, StoredFile, UserStorage


User = get_user_model()


class StorageApiTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        response = self.client.get("/api/accounts/csrf/")
        self.csrf_token = response.json()["csrfToken"]
        self.user = User.objects.create_user(username="owner", password="StrongPassword123!")
        self.other_user = User.objects.create_user(username="other", password="StrongPassword123!")
        plan = StoragePlan.objects.create(name="Free", quota_bytes=10_000)
        UserStorage.objects.create(user=self.user, plan=plan)

    def test_private_dashboard_requires_authentication(self):
        response = self.client.get("/api/storage/dashboard/")
        self.assertEqual(response.status_code, 401)

    def test_upload_and_list_are_owner_scoped(self):
        self.client.force_login(self.user)
        uploaded = SimpleUploadedFile("note.txt", b"private content", content_type="text/plain")
        response = self.client.post(
            "/api/storage/files/upload/",
            {"file": uploaded},
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )
        self.assertEqual(response.status_code, 201)
        file_id = response.json()["file_id"]

        response = self.client.get("/api/storage/files/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["files"]), 1)

        self.client.force_login(self.other_user)
        response = self.client.get(f"/api/storage/files/{file_id}/download/")
        self.assertEqual(response.status_code, 404)

    def test_upload_rejects_quota_overflow(self):
        self.client.force_login(self.user)
        uploaded = SimpleUploadedFile("large.bin", b"x" * 10_001, content_type="application/octet-stream")
        response = self.client.post(
            "/api/storage/files/upload/",
            {"file": uploaded},
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )
        self.assertEqual(response.status_code, 413)
        self.assertFalse(StoredFile.objects.exists())
