import io
import json

from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings

from .pdf_rendering import IsolatedPdfRendererClient, PdfRenderingError, PdfiumRenderer
from .image_comparison import compare_images


def _image_bytes(fmt, color, size=(2, 2), **kwargs):
    output = io.BytesIO()
    mode = "RGB" if fmt == "JPEG" else "RGBA"
    image = Image.new(mode, size, color[:3] if mode == "RGB" else color)
    image.save(output, format=fmt, **kwargs)
    return output.getvalue()


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
        png = _image_bytes("PNG", (10, 20, 30, 255), size=(1, 1))
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
        self.assertTrue(comparison["image_comparison"]["same_visual"])

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
        png = _image_bytes("PNG", (10, 20, 30, 255), size=(1, 1))
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

    def test_isolated_renderer_uses_a_worker_process(self):
        pdf = _pdf_with_text("worker")
        renderer = IsolatedPdfRendererClient(timeout_seconds=20)

        result = renderer.compare(pdf, pdf)

        self.assertEqual(result["first"]["page_count"], 1)
        self.assertNotEqual(renderer.last_worker_pid, __import__("os").getpid())

    def test_isolated_renderer_terminates_after_hard_timeout(self):
        pdf = _pdf_with_text("timeout")
        renderer = IsolatedPdfRendererClient(timeout_seconds=0.001)

        with self.assertRaisesRegex(PdfRenderingError, "hard worker timeout"):
            renderer.compare(pdf, pdf)


class ImageComparisonTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        response = self.client.get("/api/accounts/csrf/")
        self.csrf_token = response.json()["csrfToken"]

    def test_modified_image_has_pixel_difference_and_preview(self):
        first = _image_bytes("PNG", (255, 255, 255, 255))
        second = _image_bytes("PNG", (255, 0, 0, 255))

        result = compare_images(first, second)

        self.assertFalse(result["same_visual"])
        self.assertEqual(result["visual_differences"], 1)
        self.assertGreater(result["frame_results"][0]["visual"]["difference_percentage"], 0)
        self.assertIsNotNone(result["frame_results"][0]["visual"]["overlay_png"])

    def test_resized_image_reports_dimension_difference(self):
        first = _image_bytes("JPEG", (255, 255, 255, 255), size=(2, 2))
        second = _image_bytes("JPEG", (255, 255, 255, 255), size=(3, 3))

        result = compare_images(first, second)

        self.assertFalse(result["same_visual"])
        self.assertFalse(result["frame_results"][0]["visual"]["same_dimensions"])

    def test_transparent_rgb_differences_are_not_visible_differences(self):
        first = _image_bytes("PNG", (255, 0, 0, 0))
        second = _image_bytes("PNG", (0, 255, 0, 0))

        self.assertTrue(compare_images(first, second)["same_visual"])

    def test_animated_gif_compares_each_frame(self):
        output_first = io.BytesIO()
        Image.new("RGB", (2, 2), "red").save(
            output_first,
            format="GIF",
            save_all=True,
            append_images=[Image.new("RGB", (2, 2), "blue")],
            duration=[100, 100],
            loop=0,
        )
        output_second = io.BytesIO()
        Image.new("RGB", (2, 2), "red").save(
            output_second,
            format="GIF",
            save_all=True,
            append_images=[Image.new("RGB", (2, 2), "green")],
            duration=[100, 100],
            loop=0,
        )

        result = compare_images(output_first.getvalue(), output_second.getvalue())

        self.assertTrue(result["animated"])
        self.assertEqual(len(result["frame_results"]), 2)

    def test_malformed_image_is_rejected_by_api(self):
        response = self.client.post(
            "/api/tools/compare/",
            {
                "first": SimpleUploadedFile("first.webp", b"RIFFbadWEBP", content_type="image/webp"),
                "second": SimpleUploadedFile("second.webp", b"RIFFbadWEBP", content_type="image/webp"),
            },
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )

        self.assertEqual(response.status_code, 400)
