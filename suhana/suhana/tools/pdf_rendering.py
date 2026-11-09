import base64
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
import threading
import time
import zlib
from dataclasses import dataclass

PDF_MAX_PAGES = 100
PDF_DEFAULT_DPI = 120
PDF_MAX_DPI = 150
PDF_MAX_PAGE_PIXELS = 8_192
PDF_MAX_PIXELS_PER_DOCUMENT = 80_000_000
PDF_MAX_COMBINED_PIXELS = 160_000_000
PDF_SOFT_TIMEOUT_SECONDS = 20
PDF_MAX_OVERLAY_BYTES = 1_000_000


class PdfRenderingError(ValueError):
    """A PDF cannot be safely inspected or rendered within the configured limits."""


@dataclass(frozen=True)
class _PageImage:
    width: int
    height: int
    channels: int
    stride: int
    data: bytes


def _normalise_text(value):
    return re.sub(r"\s+", " ", value or "").strip()


def _png_chunk(kind, data):
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


def _overlay_png(width, height, differing, max_bytes=PDF_MAX_OVERLAY_BYTES):
    rows = []
    for row in differing:
        encoded = bytearray([0])
        for changed in row:
            encoded.extend((255, 0, 0, 180) if changed else (0, 0, 0, 0))
        rows.append(bytes(encoded))
    payload = zlib.compress(b"".join(rows), level=6)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + _png_chunk(b"IDAT", payload)
        + _png_chunk(b"IEND", b"")
    )
    if len(png) > max_bytes:
        return None
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def _read_bitmap(bitmap):
    return _PageImage(
        width=bitmap.width,
        height=bitmap.height,
        channels=bitmap.n_channels,
        stride=bitmap.stride,
        data=bytes(bitmap.buffer),
    )


def _compare_images(first, second):
    if (first.width, first.height, first.channels) != (
        second.width,
        second.height,
        second.channels,
    ):
        return {
            "same_dimensions": False,
            "differing_pixels": None,
            "difference_percentage": 100.0,
            "bounding_box": None,
            "overlay_png": None,
        }

    rows = []
    differing_pixels = 0
    min_x, min_y = first.width, first.height
    max_x = max_y = -1
    for y in range(first.height):
        first_row = first.data[y * first.stride : y * first.stride + first.width * first.channels]
        second_row = second.data[y * second.stride : y * second.stride + second.width * second.channels]
        changed_row = []
        for x in range(first.width):
            start = x * first.channels
            changed = first_row[start : start + first.channels] != second_row[
                start : start + second.channels
            ]
            changed_row.append(changed)
            if changed:
                differing_pixels += 1
                min_x, max_x = min(min_x, x), max(max_x, x)
                min_y, max_y = min(min_y, y), max(max_y, y)
        rows.append(changed_row)

    total_pixels = first.width * first.height
    return {
        "same_dimensions": True,
        "differing_pixels": differing_pixels,
        "difference_percentage": round(differing_pixels * 100 / total_pixels, 6),
        "bounding_box": None
        if max_x < 0
        else {"left": min_x, "top": min_y, "right": max_x, "bottom": max_y},
        "overlay_png": _overlay_png(first.width, first.height, rows),
    }


class PDFRenderer:
    """Renderer interface used by the comparison service."""

    def compare(self, first_bytes, second_bytes):
        raise NotImplementedError

    def inspect(self, data):
        raise NotImplementedError


class PdfiumRenderer(PDFRenderer):
    def __init__(self, dpi=PDF_DEFAULT_DPI):
        if dpi <= 0 or dpi > PDF_MAX_DPI:
            raise PdfRenderingError(f"PDF rendering DPI must be between 1 and {PDF_MAX_DPI}.")
        self.dpi = dpi

    def _open(self, data):
        import pypdfium2 as pdfium

        if not data.startswith(b"%PDF-"):
            raise PdfRenderingError("The uploaded file is not a valid PDF.")
        try:
            return pdfium.PdfDocument(data)
        except Exception as error:
            raise PdfRenderingError("The PDF is malformed, encrypted, or unsupported.") from error

    def _inspect(self, data, started):
        document = self._open(data)
        page_count = len(document)
        if page_count > PDF_MAX_PAGES:
            document.close()
            raise PdfRenderingError(f"PDFs may contain at most {PDF_MAX_PAGES} pages.")

        pages = []
        total_pixels = 0
        has_text = False
        try:
            for index in range(page_count):
                if time.monotonic() - started > PDF_SOFT_TIMEOUT_SECONDS:
                    raise PdfRenderingError("PDF comparison exceeded the 20-second processing budget.")
                page = document[index]
                width, height = page.get_size()
                pixel_width = max(1, round(width * self.dpi / 72))
                pixel_height = max(1, round(height * self.dpi / 72))
                if pixel_width > PDF_MAX_PAGE_PIXELS or pixel_height > PDF_MAX_PAGE_PIXELS:
                    raise PdfRenderingError("A PDF page exceeds the maximum rendered dimensions.")
                total_pixels += pixel_width * pixel_height
                if total_pixels > PDF_MAX_PIXELS_PER_DOCUMENT:
                    raise PdfRenderingError("A PDF exceeds the rendered pixel budget.")
                text = _normalise_text(page.get_textpage().get_text_range())
                has_text = has_text or bool(text)
                pages.append({"index": index + 1, "text": text, "width": pixel_width, "height": pixel_height})
        finally:
            document.close()
        return {"page_count": page_count, "has_text": has_text, "pages": pages}

    def inspect(self, data):
        return self._inspect(data, time.monotonic())

    def _render_page(self, data, index):
        document = self._open(data)
        try:
            page = document[index]
            return _read_bitmap(page.render(scale=self.dpi / 72))
        finally:
            document.close()

    def compare(self, first_bytes, second_bytes):
        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="suhana-pdf-") as _job_directory:
            first = self._inspect(first_bytes, started)
            second = self._inspect(second_bytes, started)
            combined_pixels = sum(
                page["width"] * page["height"] for page in first["pages"] + second["pages"]
            )
            if combined_pixels > PDF_MAX_COMBINED_PIXELS:
                raise PdfRenderingError("The PDF pair exceeds the combined rendered pixel budget.")

            page_results = []
            common_pages = min(first["page_count"], second["page_count"])
            for index in range(common_pages):
                if time.monotonic() - started > PDF_SOFT_TIMEOUT_SECONDS:
                    raise PdfRenderingError("PDF comparison exceeded the 20-second processing budget.")
                first_image = self._render_page(first_bytes, index)
                second_image = self._render_page(second_bytes, index)
                visual = _compare_images(first_image, second_image)
                page_results.append(
                    {
                        "page": index + 1,
                        "text_same": first["pages"][index]["text"] == second["pages"][index]["text"],
                        "first_text": first["pages"][index]["text"],
                        "second_text": second["pages"][index]["text"],
                        "visual": visual,
                    }
                )
            for index in range(common_pages, first["page_count"]):
                page_results.append(
                    {"page": index + 1, "status": "removed", "text_same": False, "visual": None}
                )
            for index in range(common_pages, second["page_count"]):
                page_results.append(
                    {"page": index + 1, "status": "added", "text_same": False, "visual": None}
                )

        return {
            "renderer": "pypdfium2",
            "dpi": self.dpi,
            "first": {
                "page_count": first["page_count"],
                "has_text_layer": first["has_text"],
                "scanned_likely": not first["has_text"],
            },
            "second": {
                "page_count": second["page_count"],
                "has_text_layer": second["has_text"],
                "scanned_likely": not second["has_text"],
            },
            "page_results": page_results,
            "text_differences": sum(1 for page in page_results if not page["text_same"]),
            "visual_differences": sum(
                1
                for page in page_results
                if page["visual"] and page["visual"]["difference_percentage"] > 0
            ),
            "overlays_are_temporary": True,
        }


_PDF_PROCESS_LIMIT = 2
_PDF_PROCESS_SLOTS = threading.BoundedSemaphore(_PDF_PROCESS_LIMIT)


class IsolatedPdfRendererClient(PDFRenderer):
    def __init__(self, timeout_seconds=PDF_SOFT_TIMEOUT_SECONDS):
        self.timeout_seconds = timeout_seconds
        self.last_worker_pid = None

    def _run(self, operation, first_bytes, second_bytes=None):
        if not _PDF_PROCESS_SLOTS.acquire(timeout=self.timeout_seconds):
            raise PdfRenderingError("PDF processing capacity is currently exhausted.")
        try:
            with tempfile.TemporaryDirectory(prefix="suhana-pdf-client-") as directory:
                from pathlib import Path

                job = Path(directory)
                first_path = job / "first.pdf"
                output_path = job / "result.json"
                first_path.write_bytes(first_bytes)
                command = [
                    sys.executable,
                    "-m",
                    "tools.pdf_worker",
                    operation,
                    str(first_path),
                    str(output_path),
                ]
                if second_bytes is not None:
                    second_path = job / "second.pdf"
                    second_path.write_bytes(second_bytes)
                    command.append(str(second_path))
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=str(Path(__file__).resolve().parents[1]),
                    text=True,
                )
                try:
                    stdout, stderr = process.communicate(timeout=self.timeout_seconds)
                except subprocess.TimeoutExpired as error:
                    process.kill()
                    process.communicate()
                    raise PdfRenderingError(
                        "PDF comparison exceeded the hard worker timeout."
                    ) from error
                if process.returncode != 0:
                    try:
                        payload = json.loads(output_path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        payload = {}
                    raise PdfRenderingError(
                        payload.get("error")
                        or "The isolated PDF renderer rejected the document."
                    )
                try:
                    payload = json.loads(output_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as error:
                    raise PdfRenderingError(
                        "The isolated PDF renderer returned invalid output."
                    ) from error
                self.last_worker_pid = payload.pop("worker_pid", None)
                return payload
        finally:
            _PDF_PROCESS_SLOTS.release()

    def inspect(self, data):
        return self._run("inspect", data)

    def compare(self, first_bytes, second_bytes):
        return self._run("compare", first_bytes, second_bytes)
