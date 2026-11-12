import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings

from .models import Folder, StoragePlan, StoredFile, UserStorage


User = get_user_model()


class StorageApiTests(TestCase):
    def setUp(self):
        media_root = tempfile.TemporaryDirectory(prefix="suhana-storage-test-")
        self.addCleanup(media_root.cleanup)
        media_settings = override_settings(MEDIA_ROOT=media_root.name)
        media_settings.enable()
        self.addCleanup(media_settings.disable)
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

    def test_dashboard_returns_storage_balance_and_recent_file_data(self):
        self.client.force_login(self.user)
        stored = StoredFile.objects.create(
            owner=self.user,
            name="dashboard.txt",
            file=SimpleUploadedFile("dashboard.txt", b"stored"),
            size_bytes=6,
            content_type="text/plain",
        )
        storage = UserStorage.objects.get(user=self.user)
        storage.used_bytes = 6
        storage.save(update_fields=["used_bytes"])

        response = self.client.get("/api/storage/dashboard/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["storage"]["used_bytes"], 6)
        self.assertEqual(response.json()["storage"]["available_bytes"], 9_994)
        self.assertEqual(response.json()["recent_files"][0]["id"], stored.id)
        self.assertEqual(response.json()["recent_activities"], [])

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

    def test_folder_creation_and_rename_are_owner_scoped(self):
        self.client.force_login(self.user)
        response = self.client.post(
            "/api/storage/folders/",
            {"name": "Reports"},
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )
        self.assertEqual(response.status_code, 201)
        folder_id = response.json()["folder_id"]

        response = self.client.post(
            f"/api/storage/folders/{folder_id}/rename/",
            {"name": "Saved reports"},
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Folder.objects.get(pk=folder_id).name, "Saved reports")

        self.client.force_login(self.other_user)
        response = self.client.post(
            f"/api/storage/folders/{folder_id}/rename/",
            {"name": "Private"},
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )
        self.assertEqual(response.status_code, 404)

    def test_file_rename_and_move_preserve_storage_usage(self):
        self.client.force_login(self.user)
        first_folder = Folder.objects.create(owner=self.user, name="First")
        second_folder = Folder.objects.create(owner=self.user, name="Second")
        stored = StoredFile.objects.create(
            owner=self.user,
            folder=first_folder,
            name="note.txt",
            file=SimpleUploadedFile("note.txt", b"private content"),
            size_bytes=15,
            content_type="text/plain",
        )
        storage = UserStorage.objects.get(user=self.user)
        storage.used_bytes = 15
        storage.save(update_fields=["used_bytes"])

        renamed = self.client.post(
            f"/api/storage/files/{stored.id}/rename/",
            {"name": "renamed.txt"},
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )
        moved = self.client.post(
            f"/api/storage/files/{stored.id}/move/",
            {"folder": second_folder.id},
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )

        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(moved.status_code, 200)
        stored.refresh_from_db()
        storage.refresh_from_db()
        self.assertEqual(stored.name, "renamed.txt")
        self.assertEqual(stored.folder_id, second_folder.id)
        self.assertEqual(storage.used_bytes, 15)

        moved_to_root = self.client.post(
            f"/api/storage/files/{stored.id}/move/",
            {"folder": ""},
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )
        self.assertEqual(moved_to_root.status_code, 200)
        stored.refresh_from_db()
        self.assertIsNone(stored.folder_id)

    def test_file_rename_and_move_reject_other_users_and_name_collisions(self):
        self.client.force_login(self.user)
        folder = Folder.objects.create(owner=self.user, name="Reports")
        other_folder = Folder.objects.create(owner=self.other_user, name="Private")
        first = StoredFile.objects.create(
            owner=self.user, folder=folder, name="first.txt",
            file=SimpleUploadedFile("first.txt", b"one"), size_bytes=3,
        )
        StoredFile.objects.create(
            owner=self.user, folder=folder, name="taken.txt",
            file=SimpleUploadedFile("taken.txt", b"two"), size_bytes=3,
        )

        rename_collision = self.client.post(
            f"/api/storage/files/{first.id}/rename/",
            {"name": "taken.txt"},
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )
        move_to_other_owner = self.client.post(
            f"/api/storage/files/{first.id}/move/",
            {"folder": other_folder.id},
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )
        invalid_name = self.client.post(
            f"/api/storage/files/{first.id}/rename/",
            {"name": "..\\private.txt"},
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )

        self.assertEqual(rename_collision.status_code, 409)
        self.assertEqual(move_to_other_owner.status_code, 404)
        self.assertEqual(invalid_name.status_code, 400)
