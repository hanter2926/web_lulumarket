import io
import json

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings

from .pdf_rendering import PdfRenderingError, PdfiumRenderer


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

    def test_compare_rejects_mismatched_image_signature(self):
        response = self.client.post(
            "/api/tools/compare/",
            {
                "first": SimpleUploadedFile("first.png", b"not png", content_type="image/png"),
                "second": SimpleUploadedFile("second.png", b"not png", content_type="image/png"),
            },
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )

        self.assertEqual(response.status_code, 400)

    def test_unit_conversion_rejects_non_finite_values(self):
        for value in ("NaN", "Infinity", "-Infinity"):
            response = self.client.post(
                "/api/tools/convert/",
                data=json.dumps({"value": value, "from": "gb", "to": "mb"}),
                content_type="application/json",
                HTTP_X_CSRFTOKEN=self.csrf_token,
            )
            self.assertEqual(response.status_code, 400)

    def test_authenticated_comparison_is_saved_to_owner_history(self):
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_user(
            username="report-owner", password="StrongPassword123!"
        )
        self.client.force_login(user)
        png = (
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR"
            b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
        )
        response = self.client.post(
            "/api/tools/compare/",
            {
                "first": SimpleUploadedFile("first.png", png, content_type="image/png"),
                "second": SimpleUploadedFile("second.png", png, content_type="image/png"),
            },
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.json()["report_id"])

        response = self.client.get("/api/tools/reports/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["reports"]), 1)


def _pdf_with_text(text):
    content = f"BT /F1 24 Tf 72 720 Td ({text}) Tj ET\n".encode()
    return (
        b"%PDF-1.4\n"
        b"1 0 obj<< /Type /Catalog /Pages 2 0 R>>endobj\n"
        b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1>>endobj\n"
        b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>endobj\n"
        + f"4 0 obj<< /Length {len(content)}>>stream\n".encode()
        + content
        + b"endstream endobj\n"
        + b"5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica>>endobj\n"
        + b"trailer<< /Root 1 0 R>>\n%%EOF"
    )


class PdfRenderingTests(TestCase):
    def test_identical_pdf_has_text_and_no_visual_difference(self):
        pdf = _pdf_with_text("Hello")
        result = PdfiumRenderer(dpi=72).compare(pdf, pdf)

        self.assertEqual(result["first"]["page_count"], 1)
        self.assertTrue(result["first"]["has_text_layer"])
        self.assertTrue(result["page_results"][0]["text_same"])
        self.assertEqual(result["page_results"][0]["visual"]["difference_percentage"], 0.0)

    def test_text_difference_is_reported_separately_from_visual_difference(self):
        first = _pdf_with_text("Hello")
        second = _pdf_with_text("World")
        result = PdfiumRenderer(dpi=72).compare(first, second)

        self.assertEqual(result["text_differences"], 1)
        self.assertGreater(result["visual_differences"], 0)
        self.assertIsNotNone(result["page_results"][0]["visual"]["overlay_png"])

    def test_malformed_pdf_is_rejected(self):
        with self.assertRaises(PdfRenderingError):
            PdfiumRenderer().compare(b"not a pdf", b"not a pdf")
