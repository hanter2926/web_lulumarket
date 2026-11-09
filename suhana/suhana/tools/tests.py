import io
import json

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings


@override_settings(ROOT_URLCONF="suhana.urls")
class ToolsApiTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        response = self.client.get("/api/accounts/csrf/")
        self.csrf_token = response.json()["csrfToken"]

    def test_unit_conversion(self):
        response = self.client.post(
            "/api/tools/convert/",
            data=json.dumps({"value": 1, "from": "gb", "to": "mb"}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"], 1000)

    def test_unit_conversion_rejects_negative_values(self):
        response = self.client.post(
            "/api/tools/convert/",
            data=json.dumps({"value": -1, "from": "gb", "to": "mb"}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )

        self.assertEqual(response.status_code, 400)

    def test_identical_png_files_compare_equal(self):
        png = (
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR"
            b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
        )
        first = SimpleUploadedFile("first.png", io.BytesIO(png).read(), content_type="image/png")
        second = SimpleUploadedFile("second.png", png, content_type="image/png")

        response = self.client.post(
            "/api/tools/compare/",
            {"first": first, "second": second},
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )

        self.assertEqual(response.status_code, 200)
        comparison = response.json()["comparison"]
        self.assertTrue(comparison["same_content"])
        self.assertEqual(comparison["first"]["dimensions"], [1, 1])

    def test_compare_requires_both_supported_files(self):
        first = SimpleUploadedFile("first.txt", b"one", content_type="text/plain")
        second = SimpleUploadedFile("second.txt", b"two", content_type="text/plain")

        response = self.client.post(
            "/api/tools/compare/",
            {"first": first, "second": second},
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )

        self.assertEqual(response.status_code, 400)
