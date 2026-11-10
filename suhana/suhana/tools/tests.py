import io
import json
import os
import sys
import tempfile
import time
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from .models import ComparisonJob, ComparisonQueueControl
from .processing_jobs import cleanup_expired_jobs
from .image_comparison import compare_images, image_metadata
from .pdf_rendering import IsolatedPdfRendererClient, PdfRenderingError, PdfiumRenderer
from .process_runner import (
    ProcessCancelledError,
    ProcessTimeoutError,
    run_limited_process,
)


def _image_bytes(fmt, color, size=(2, 2), **kwargs):
    output = io.BytesIO()
    mode = "RGB" if fmt == "JPEG" else "RGBA"
    image = Image.new(mode, size, color[:3] if mode == "RGB" else color)
    image.save(output, format=fmt, **kwargs)
    return output.getvalue()


@override_settings(ROOT_URLCONF="suhana.urls")
class ToolsApiTests(TransactionTestCase):
    def setUp(self):
        private_root = tempfile.TemporaryDirectory(prefix="suhana-jobs-test-")
        self.addCleanup(private_root.cleanup)
        self.private_root = Path(private_root.name)
        settings_override = override_settings(PROCESSING_JOB_ROOT=self.private_root)
        settings_override.enable()
        self.addCleanup(settings_override.disable)
        ComparisonQueueControl.objects.get_or_create(pk=1)
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

        self.assertEqual(response.status_code, 202)
        accepted = response.json()
        job_id = accepted["job_id"]
        self.assertEqual(accepted["status"], ComparisonJob.Status.QUEUED)
        self.assertTrue((self.private_root / job_id).is_dir())
        call_command("run_comparison_worker", once=True, stdout=io.StringIO())
        status = self.client.get(
            accepted["status_url"],
            HTTP_X_JOB_TOKEN=accepted["job_token"],
        )
        self.assertEqual(status.status_code, 200)
        self.assertIn("no-store", status["Cache-Control"])
        comparison = status.json()["comparison"]
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
        self.assertEqual(response.status_code, 202)
        accepted = response.json()
        call_command("run_comparison_worker", once=True, stdout=io.StringIO())

        response = self.client.get("/api/tools/reports/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["reports"]), 1)

    def test_comparison_job_requires_its_capability_token(self):
        png = _image_bytes("PNG", (10, 20, 30, 255), size=(1, 1))
        response = self.client.post(
            "/api/tools/compare/",
            {
                "first": SimpleUploadedFile("first.png", png, content_type="image/png"),
                "second": SimpleUploadedFile("second.png", png, content_type="image/png"),
            },
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )

        status = self.client.get(
            response.json()["status_url"],
            HTTP_X_JOB_TOKEN="wrong-token",
        )

        self.assertEqual(status.status_code, 404)

    def test_queued_comparison_can_be_cancelled(self):
        png = _image_bytes("PNG", (10, 20, 30, 255), size=(1, 1))
        response = self.client.post(
            "/api/tools/compare/",
            {
                "first": SimpleUploadedFile("first.png", png, content_type="image/png"),
                "second": SimpleUploadedFile("second.png", png, content_type="image/png"),
            },
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )
        accepted = response.json()

        cancelled = self.client.post(
            accepted["cancel_url"],
            HTTP_X_CSRFTOKEN=self.csrf_token,
            HTTP_X_JOB_TOKEN=accepted["job_token"],
        )

        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.json()["status"], ComparisonJob.Status.CANCELLED)
        self.assertFalse((self.private_root / accepted["job_id"]).exists())

    def test_expired_queued_job_is_cancelled_and_removed(self):
        png = _image_bytes("PNG", (10, 20, 30, 255), size=(1, 1))
        response = self.client.post(
            "/api/tools/compare/",
            {
                "first": SimpleUploadedFile("first.png", png, content_type="image/png"),
                "second": SimpleUploadedFile("second.png", png, content_type="image/png"),
            },
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )
        job_id = response.json()["job_id"]
        ComparisonJob.objects.filter(pk=job_id).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )

        cleanup_expired_jobs()

        self.assertFalse(ComparisonJob.objects.filter(pk=job_id).exists())
        self.assertFalse((self.private_root / job_id).exists())


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

    def test_supported_static_formats_decode_and_compare_identically(self):
        for fmt in ("PNG", "JPEG", "GIF", "WEBP"):
            with self.subTest(format=fmt):
                image = _image_bytes(fmt, (30, 60, 90, 255))
                result = compare_images(image, image)

                self.assertTrue(result["same_visual"])
                self.assertEqual(result["first_format"], fmt)

    def test_opaque_rgba_png_metadata_preserves_alpha_channel(self):
        image = _image_bytes("PNG", (30, 60, 90, 255))

        self.assertTrue(image_metadata(image)["has_alpha"])

    def test_animated_webp_and_apng_compare_each_frame(self):
        for fmt in ("WEBP", "PNG"):
            with self.subTest(format=fmt):
                frames = [
                    Image.new("RGBA", (2, 2), color)
                    for color in ((255, 0, 0, 255), (0, 0, 255, 255))
                ]
                output = io.BytesIO()
                frames[0].save(
                    output,
                    format=fmt,
                    save_all=True,
                    append_images=frames[1:],
                    duration=100,
                    loop=0,
                )

                result = compare_images(output.getvalue(), output.getvalue())

                self.assertTrue(result["animated"])
                self.assertEqual(len(result["frame_results"]), 2)
                self.assertTrue(result["same_visual"])

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


class ProcessIsolationTests(TestCase):
    def python_child_executable(self):
        if os.name == "nt":
            return sys._base_executable
        return sys.executable

    def test_windows_dispatch_does_not_use_posix_resource_limits(self):
        command = ["engine", "inspect", "input"]
        working_directory = Path.cwd()
        with (
            patch("tools.process_runner.os.name", "nt"),
            patch("tools.process_runner._run_windows") as windows_runner,
            patch("tools.process_runner._run_posix") as posix_runner,
        ):
            run_limited_process(command, working_directory, timeout_seconds=1)

        windows_runner.assert_called_once_with(
            command, working_directory, 1, None
        )
        posix_runner.assert_not_called()

    def test_child_timeout_terminates_the_worker(self):
        command = [self.python_child_executable(), "-c", "import time; time.sleep(10)"]

        with self.assertRaises(ProcessTimeoutError):
            run_limited_process(command, Path.cwd(), timeout_seconds=0.25)

    def test_cancellation_terminates_the_worker(self):
        command = [self.python_child_executable(), "-c", "import time; time.sleep(10)"]
        cancel_at = time.monotonic() + 0.25

        with self.assertRaises(ProcessCancelledError):
            run_limited_process(
                command,
                Path.cwd(),
                timeout_seconds=5,
                cancel_check=lambda: time.monotonic() >= cancel_at,
            )

    def test_crashed_child_does_not_affect_later_worker(self):
        crashed = run_limited_process(
            [self.python_child_executable(), "-c", "import os; os._exit(37)"],
            Path.cwd(),
            timeout_seconds=5,
        )
        healthy = run_limited_process(
            [self.python_child_executable(), "-c", "print('alive')"],
            Path.cwd(),
            timeout_seconds=5,
        )

        self.assertEqual(crashed.returncode, 37)
        self.assertEqual(healthy.stdout.strip(), "alive")

    def test_child_cannot_exceed_os_memory_limit(self):
        if os.name == "nt":
            command = [
                r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "$ErrorActionPreference = 'Stop'; "
                "$memory = New-Object byte[] (1GB); Write-Output 'allocated'",
            ]
        else:
            command = [
                self.python_child_executable(),
                "-c",
                "memory = bytearray(1024 * 1024 * 1024)",
            ]

        result = run_limited_process(command, Path.cwd(), timeout_seconds=15)

        self.assertNotEqual(result.returncode, 0)
        if os.name == "nt":
            self.assertIn("OutOfMemoryException", result.stderr)
        else:
            self.assertIn("MemoryError", result.stderr)
