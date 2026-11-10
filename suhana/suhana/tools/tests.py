import io
import json
import os
import sys
import tempfile
import time
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageOps
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from .models import ComparisonJob, ComparisonQueueControl
from .processing_jobs import claim_next_job, cleanup_expired_jobs
from .image_comparison import compare_images, image_metadata
from .pdf_rendering import IsolatedPdfRendererClient, PdfRenderingError, PdfiumRenderer
from .process_runner import (
    ProcessCancelledError,
    ProcessTimeoutError,
    run_limited_process,
)
from .rust_engine import ProcessingEngineError, compress_image


def _image_bytes(fmt, color, size=(2, 2), **kwargs):
    output = io.BytesIO()
    mode = "RGB" if fmt == "JPEG" else "RGBA"
    image = Image.new(mode, size, color[:3] if mode == "RGB" else color)
    image.save(output, format=fmt, **kwargs)
    return output.getvalue()


def _pdf_with_redundant_content():
    content = b"% repeated content that compresses well\n" * 5_000
    content += b"BT /F1 24 Tf 72 720 Td (worker) Tj ET\n"
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
        self.assertEqual(accepted["state"], "queued")
        self.assertEqual(accepted["stage"], "Waiting for a worker.")
        self.assertTrue((self.private_root / job_id).is_dir())
        call_command("run_comparison_worker", once=True, stdout=io.StringIO())
        status = self.client.get(
            accepted["status_url"],
            HTTP_X_JOB_TOKEN=accepted["job_token"],
        )
        self.assertEqual(status.status_code, 200)
        self.assertIn("no-store", status["Cache-Control"])
        self.assertEqual(status.json()["state"], "completed")
        comparison = status.json()["comparison"]
        self.assertTrue(comparison["same_content"])
        self.assertEqual(comparison["first"]["dimensions"], [1, 1])
        self.assertTrue(comparison["image_comparison"]["same_visual"])

    def test_large_image_pair_runs_through_background_worker(self):
        pixels = os.urandom(2048 * 2048 * 3)
        image = Image.frombytes("RGB", (2048, 2048), pixels)
        output = io.BytesIO()
        image.save(output, format="PNG")
        png = output.getvalue()
        self.assertGreaterEqual(len(png), 10 * 1024 * 1024)
        self.assertLessEqual(len(png), 25 * 1024 * 1024)

        response = self.client.post(
            "/api/tools/compare/",
            {
                "first": SimpleUploadedFile("large-first.png", png, content_type="image/png"),
                "second": SimpleUploadedFile("large-second.png", png, content_type="image/png"),
            },
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )
        self.assertEqual(response.status_code, 202)
        accepted = response.json()
        call_command("run_comparison_worker", once=True, stdout=io.StringIO())

        status = self.client.get(
            accepted["status_url"],
            HTTP_X_JOB_TOKEN=accepted["job_token"],
        )
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["state"], "completed")
        self.assertEqual(status.json()["comparison"]["first"]["dimensions"], [2048, 2048])

    def test_pdf_comparison_runs_through_background_worker(self):
        pdf = _pdf_with_text("worker")
        response = self.client.post(
            "/api/tools/compare/",
            {
                "first": SimpleUploadedFile("first.pdf", pdf, content_type="application/pdf"),
                "second": SimpleUploadedFile("second.pdf", pdf, content_type="application/pdf"),
            },
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )
        self.assertEqual(response.status_code, 202)
        accepted = response.json()
        call_command("run_comparison_worker", once=True, stdout=io.StringIO())

        status = self.client.get(
            accepted["status_url"],
            HTTP_X_JOB_TOKEN=accepted["job_token"],
        )
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["state"], "completed")
        self.assertEqual(
            status.json()["comparison"]["pdf_comparison"]["first"]["page_count"],
            1,
        )

    def run_compression(self, data, name, content_type):
        response = self.client.post(
            "/api/tools/compress/",
            {"file": SimpleUploadedFile(name, data, content_type=content_type)},
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )
        self.assertEqual(response.status_code, 202, response.content)
        accepted = response.json()
        call_command("run_comparison_worker", once=True, stdout=io.StringIO())
        status = self.client.get(
            accepted["status_url"],
            HTTP_X_JOB_TOKEN=accepted["job_token"],
        )
        self.assertEqual(status.status_code, 200)
        return accepted, status

    def test_png_compression_produces_valid_download_and_checks_real_size(self):
        image = Image.new("RGB", (512, 512), (20, 40, 60))
        source = io.BytesIO()
        image.save(source, format="PNG", compress_level=0)
        original = source.getvalue()

        accepted, status = self.run_compression(original, "photo.png", "image/png")

        self.assertEqual(status.json()["state"], "completed")
        compression = status.json()["compression"]
        self.assertEqual(compression["input_bytes"], len(original))
        self.assertLess(compression["output_bytes"], len(original))
        self.assertEqual(compression["saved_bytes"], len(original) - compression["output_bytes"])

        denied = self.client.get(status.json()["download_url"])
        self.assertEqual(denied.status_code, 404)
        download = self.client.get(
            status.json()["download_url"],
            HTTP_X_JOB_TOKEN=accepted["job_token"],
        )
        self.assertEqual(download.status_code, 200)
        output = b"".join(download.streaming_content)
        self.assertEqual(len(output), compression["output_bytes"])
        self.assertEqual(output[:8], b"\x89PNG\r\n\x1a\n")
        with Image.open(io.BytesIO(output)) as compressed:
            self.assertEqual(compressed.size, image.size)
            self.assertEqual(compressed.convert("RGB").getpixel((0, 0)), image.getpixel((0, 0)))

    def test_large_image_compression_stays_within_resource_and_output_limits(self):
        pixels = os.urandom(2048 * 2048 * 3)
        image = Image.frombytes("RGB", (2048, 2048), pixels)
        source = io.BytesIO()
        image.save(source, format="PNG", compress_level=0)
        original = source.getvalue()
        self.assertGreater(len(original), 10 * 1024 * 1024)
        self.assertLessEqual(len(original), 25 * 1024 * 1024)

        accepted, status = self.run_compression(original, "large.png", "image/png")

        self.assertEqual(status.json()["state"], "completed")
        compression = status.json()["compression"]
        self.assertEqual(compression["input_bytes"], len(original))
        self.assertGreater(compression["output_bytes"], 0)
        self.assertLessEqual(compression["output_bytes"], 25 * 1024 * 1024)
        download = self.client.get(
            status.json()["download_url"],
            HTTP_X_JOB_TOKEN=accepted["job_token"],
        )
        self.assertEqual(download.status_code, 200)
        downloaded = b"".join(download.streaming_content)
        self.assertEqual(len(downloaded), compression["output_bytes"])

    def test_pdf_compression_preserves_rendered_content_and_page_count(self):
        original = _pdf_with_redundant_content()
        accepted, status = self.run_compression(original, "report.pdf", "application/pdf")

        self.assertEqual(status.json()["state"], "completed")
        compression = status.json()["compression"]
        self.assertLess(compression["output_bytes"], len(original))
        self.assertEqual(compression["page_count"], 1)
        download = self.client.get(
            status.json()["download_url"],
            HTTP_X_JOB_TOKEN=accepted["job_token"],
        )
        output = b"".join(download.streaming_content)
        self.assertEqual(len(output), compression["output_bytes"])
        self.assertTrue(output.startswith(b"%PDF-"))
        comparison = PdfiumRenderer(dpi=72).compare(original, output)
        self.assertEqual(comparison["first"]["page_count"], comparison["second"]["page_count"])
        self.assertEqual(comparison["text_differences"], 0)
        self.assertEqual(comparison["visual_differences"], 0)

    def test_jpeg_gif_and_webp_compression_keep_their_formats(self):
        jpeg = _image_bytes("JPEG", (100, 120, 140), size=(32, 32))
        jpeg_accepted, jpeg_status = self.run_compression(jpeg, "photo.jpg", "image/jpeg")
        self.assertEqual(jpeg_status.json()["state"], "completed")
        jpeg_download = self.client.get(
            jpeg_status.json()["download_url"],
            HTTP_X_JOB_TOKEN=jpeg_accepted["job_token"],
        )
        with Image.open(io.BytesIO(b"".join(jpeg_download.streaming_content))) as image:
            self.assertEqual(image.format, "JPEG")

        first = Image.new("RGBA", (16, 16), (255, 0, 0, 255))
        second = Image.new("RGBA", (16, 16), (0, 255, 0, 255))
        gif_buffer = io.BytesIO()
        first.save(
            gif_buffer,
            format="GIF",
            save_all=True,
            append_images=[second],
            duration=[100, 200],
            loop=0,
        )
        gif_accepted, gif_status = self.run_compression(
            gif_buffer.getvalue(), "animation.gif", "image/gif"
        )
        self.assertEqual(gif_status.json()["state"], "completed")
        gif_output = self.client.get(
            gif_status.json()["download_url"],
            HTTP_X_JOB_TOKEN=gif_accepted["job_token"],
        )
        gif_frames = []
        with Image.open(io.BytesIO(b"".join(gif_output.streaming_content))) as image:
            self.assertEqual(image.format, "GIF")
            self.assertEqual(image.n_frames, 2)
            for frame_index in range(image.n_frames):
                image.seek(frame_index)
                gif_frames.append(image.convert("RGB").getpixel((0, 0)))
        self.assertEqual(gif_frames, [(255, 0, 0), (0, 255, 0)])

        webp = _image_bytes("WEBP", (100, 120, 140), size=(32, 32))
        accepted, webp_status = self.run_compression(webp, "photo.webp", "image/webp")
        self.assertEqual(webp_status.json()["state"], "completed")
        webp_download = self.client.get(
            webp_status.json()["download_url"],
            HTTP_X_JOB_TOKEN=accepted["job_token"],
        )
        output = b"".join(webp_download.streaming_content)
        with Image.open(io.BytesIO(webp)) as original:
            original_pixel = original.convert("RGBA").getpixel((0, 0))
        with Image.open(io.BytesIO(output)) as image:
            self.assertEqual(image.format, "WEBP")
            self.assertEqual(image.convert("RGBA").getpixel((0, 0)), original_pixel)

    def test_jpeg_compression_applies_exif_orientation(self):
        image = Image.new("RGB", (32, 16), (90, 120, 150))
        exif = Image.Exif()
        exif[274] = 6
        source = io.BytesIO()
        image.save(source, format="JPEG", quality=95, exif=exif)

        accepted, status = self.run_compression(source.getvalue(), "oriented.jpg", "image/jpeg")
        download = self.client.get(
            status.json()["download_url"],
            HTTP_X_JOB_TOKEN=accepted["job_token"],
        )

        with Image.open(io.BytesIO(b"".join(download.streaming_content))) as compressed:
            self.assertEqual(compressed.size, (16, 32))
            self.assertEqual(compressed.getexif().get(274, 1), 1)

    def test_compression_rejects_unsupported_and_mismatched_files(self):
        unsupported = self.client.post(
            "/api/tools/compress/",
            {"file": SimpleUploadedFile("file.txt", b"no", content_type="text/plain")},
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )
        self.assertEqual(unsupported.status_code, 400)
        self.assertIn("Only PNG", unsupported.json()["message"])

        mismatched = self.client.post(
            "/api/tools/compress/",
            {
                "file": SimpleUploadedFile(
                    "file.png", b"not a PNG", content_type="image/png"
                )
            },
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )
        self.assertEqual(mismatched.status_code, 400)

    def test_compression_rejects_files_over_the_input_limit(self):
        response = self.client.post(
            "/api/tools/compress/",
            {
                "file": SimpleUploadedFile(
                    "large.png",
                    b"\x89PNG\r\n\x1a\n" + b"x" * (25 * 1024 * 1024),
                    content_type="image/png",
                )
            },
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("25 MB", response.json()["message"])

    def test_worker_failure_is_reported_and_later_compression_recovers(self):
        image = _image_bytes("PNG", (10, 20, 30, 255), size=(32, 32))
        failed = self.client.post(
            "/api/tools/compress/",
            {"file": SimpleUploadedFile("failed.png", image, content_type="image/png")},
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )
        accepted = failed.json()
        with patch(
            "tools.processing_jobs.compress_image",
            side_effect=ProcessingEngineError("The isolated Rust processing engine failed."),
        ):
            call_command("run_comparison_worker", once=True, stdout=io.StringIO())
        failure_status = self.client.get(
            accepted["status_url"],
            HTTP_X_JOB_TOKEN=accepted["job_token"],
        )
        self.assertEqual(failure_status.json()["state"], "failed")
        self.assertIn("isolated Rust processing engine failed", failure_status.json()["message"])

        _, recovered = self.run_compression(image, "recovered.png", "image/png")
        self.assertEqual(recovered.json()["state"], "completed")

    def test_invalid_compression_output_is_never_marked_complete(self):
        image = _image_bytes("PNG", (10, 20, 30, 255), size=(32, 32))
        response = self.client.post(
            "/api/tools/compress/",
            {"file": SimpleUploadedFile("invalid-output.png", image, content_type="image/png")},
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )
        accepted = response.json()
        with patch(
            "tools.processing_jobs.compress_image",
            return_value=(
                {"input_bytes": len(image), "output_bytes": 3},
                b"bad",
            ),
        ):
            call_command("run_comparison_worker", once=True, stdout=io.StringIO())

        status = self.client.get(
            accepted["status_url"],
            HTTP_X_JOB_TOKEN=accepted["job_token"],
        )
        self.assertEqual(status.json()["state"], "failed")
        self.assertFalse((self.private_root / accepted["job_id"]).exists())

    def test_queued_compression_cancellation_removes_private_input(self):
        image = _image_bytes("PNG", (10, 20, 30, 255), size=(32, 32))
        response = self.client.post(
            "/api/tools/compress/",
            {"file": SimpleUploadedFile("cancel.png", image, content_type="image/png")},
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )
        accepted = response.json()
        job_directory = self.private_root / accepted["job_id"]
        self.assertTrue(job_directory.is_dir())

        cancelled = self.client.post(
            accepted["cancel_url"],
            HTTP_X_CSRFTOKEN=self.csrf_token,
            HTTP_X_JOB_TOKEN=accepted["job_token"],
        )

        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.json()["state"], "cancelled")
        self.assertFalse(job_directory.exists())

    def test_completed_compression_files_expire_with_the_job(self):
        image = _image_bytes("PNG", (10, 20, 30, 255), size=(32, 32))
        accepted, _ = self.run_compression(image, "expired.png", "image/png")
        job_directory = self.private_root / accepted["job_id"]
        self.assertTrue((job_directory / "output").is_file())
        ComparisonJob.objects.filter(pk=accepted["job_id"]).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )

        cleanup_expired_jobs()

        self.assertFalse(ComparisonJob.objects.filter(pk=accepted["job_id"]).exists())
        self.assertFalse(job_directory.exists())

    def test_compare_requires_both_supported_files(self):
        first = SimpleUploadedFile("first.txt", b"one", content_type="text/plain")
        second = SimpleUploadedFile("second.txt", b"two", content_type="text/plain")

        response = self.client.post(
            "/api/tools/compare/",
            {"first": first, "second": second},
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )

        self.assertEqual(response.status_code, 400)

    def test_compare_queue_exception_is_logged_and_returns_safe_json(self):
        image = _image_bytes("PNG", (10, 20, 30, 255), size=(2, 2))
        with patch(
            "tools.views.enqueue_comparison",
            side_effect=RuntimeError("private internal diagnostic"),
        ):
            with self.assertLogs("tools.views", level="ERROR") as captured:
                response = self.client.post(
                    "/api/tools/compare/",
                    {
                        "first": SimpleUploadedFile("first.png", image, content_type="image/png"),
                        "second": SimpleUploadedFile("second.png", image, content_type="image/png"),
                    },
                    HTTP_X_CSRFTOKEN=self.csrf_token,
                )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json()["message"],
            "The comparison could not be started. Please try again.",
        )
        self.assertNotIn("private internal diagnostic", response.content.decode())
        self.assertIn("private internal diagnostic", captured.output[0])

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

    def test_compare_uses_file_signature_when_browser_mime_is_wrong(self):
        png = _image_bytes("PNG", (10, 20, 30, 255), size=(2, 2))
        response = self.client.post(
            "/api/tools/compare/",
            {
                "first": SimpleUploadedFile("first.png", png, content_type="image/jpeg"),
                "second": SimpleUploadedFile("second.png", png, content_type="image/png"),
            },
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )

        self.assertEqual(response.status_code, 202, response.content)
        accepted = response.json()
        job = ComparisonJob.objects.get(pk=accepted["job_id"])
        self.assertEqual(job.first_content_type, "image/png")
        self.assertEqual(job.second_content_type, "image/png")
        call_command("run_comparison_worker", once=True, stdout=io.StringIO())
        status = self.client.get(
            accepted["status_url"],
            HTTP_X_JOB_TOKEN=accepted["job_token"],
        )
        self.assertEqual(status.json()["state"], "completed")
        self.assertTrue(status.json()["comparison"]["image_comparison"]["same_visual"])

    def test_compression_uses_file_signature_when_browser_mime_is_wrong(self):
        png = _image_bytes("PNG", (10, 20, 30, 255), size=(16, 16))
        accepted, status = self.run_compression(png, "photo.png", "image/jpeg")

        self.assertEqual(status.json()["state"], "completed")
        job = ComparisonJob.objects.get(pk=accepted["job_id"])
        self.assertEqual(job.first_content_type, "image/png")
        downloaded = self.client.get(
            status.json()["download_url"],
            HTTP_X_JOB_TOKEN=accepted["job_token"],
        )
        output = b"".join(downloaded.streaming_content)
        with Image.open(io.BytesIO(output)) as image:
            self.assertEqual(image.format, "PNG")

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
        self.assertEqual(cancelled.json()["state"], "cancelled")
        self.assertFalse((self.private_root / accepted["job_id"]).exists())

    def test_running_comparison_reports_processing_state(self):
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

        self.assertEqual(str(claim_next_job()), accepted["job_id"])
        self.assertIsNone(claim_next_job())
        status = self.client.get(
            accepted["status_url"],
            HTTP_X_JOB_TOKEN=accepted["job_token"],
        )
        self.assertEqual(status.json()["state"], "processing")
        self.assertEqual(status.json()["stage"], "Comparing files.")

    @patch(
        "tools.comparison.compare_image_pair_with_metadata",
        return_value=(
            {"same_visual": True},
            {
                "dimensions": [1, 1],
                "format": "PNG",
                "animated": False,
                "frame_count": 1,
                "has_alpha": True,
            },
            {
                "dimensions": [1, 1],
                "format": "PNG",
                "animated": False,
                "frame_count": 1,
                "has_alpha": True,
            },
        ),
    )
    def test_invalid_engine_result_is_not_stored(self, compare_pair):
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

        with self.assertLogs("tools.processing_jobs", level="ERROR") as logs:
            call_command("run_comparison_worker", once=True, stdout=io.StringIO())

        status = self.client.get(
            accepted["status_url"],
            HTTP_X_JOB_TOKEN=accepted["job_token"],
        )
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["state"], "failed")
        self.assertIsNone(status.json().get("comparison"))
        self.assertEqual(
            status.json()["message"],
            "The comparison could not be completed.",
        )
        self.assertIn("invalid structured result", "\n".join(logs.output))

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

    def test_child_cannot_exceed_os_cpu_time_limit(self):
        command = [self.python_child_executable(), "-c", "while True: pass"]
        started = time.monotonic()
        with patch("tools.process_runner.WORKER_CPU_LIMIT_SECONDS", 1):
            result = run_limited_process(command, Path.cwd(), timeout_seconds=15)

        self.assertNotEqual(result.returncode, 0)
        self.assertLess(time.monotonic() - started, 15)

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

    def test_compression_worker_timeout_is_reported(self):
        with (
            patch("tools.rust_engine._engine_path", return_value=Path(sys.executable)),
            patch(
                "tools.rust_engine.run_limited_process",
                side_effect=ProcessTimeoutError,
            ),
            self.assertRaisesRegex(
                ProcessingEngineError,
                "20-second worker timeout",
            ),
        ):
            compress_image(b"input")

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
