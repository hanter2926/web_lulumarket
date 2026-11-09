import hashlib
import re
import struct
from pathlib import Path

from .pdf_rendering import PdfiumRenderer


MAX_COMPARISON_FILE_SIZE = 25 * 1024 * 1024
SUPPORTED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
SUPPORTED_PDF_TYPE = "application/pdf"


def _sha256(uploaded_file):
    digest = hashlib.sha256()
    for chunk in uploaded_file.chunks():
        digest.update(chunk)
    uploaded_file.seek(0)
    return digest.hexdigest()


def _image_dimensions(uploaded_file, content_type):
    header = uploaded_file.read(32)
    uploaded_file.seek(0)

    if content_type == "image/png" and header.startswith(b"\x89PNG\r\n\x1a\n"):
        return struct.unpack(">II", header[16:24])

    if content_type == "image/gif" and header[:6] in (b"GIF87a", b"GIF89a"):
        return struct.unpack("<HH", header[6:10])

    if content_type == "image/webp" and header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return None

    if content_type == "image/jpeg" and header[:2] == b"\xff\xd8":
        uploaded_file.seek(2)
        while True:
            marker_start = uploaded_file.read(1)
            if not marker_start:
                break
            if marker_start != b"\xff":
                continue
            marker = uploaded_file.read(1)
            while marker == b"\xff":
                marker = uploaded_file.read(1)
            if marker in {b"\xc0", b"\xc1", b"\xc2", b"\xc3", b"\xc5", b"\xc6", b"\xc7", b"\xc9", b"\xca", b"\xcb", b"\xcd", b"\xce", b"\xcf"}:
                length_bytes = uploaded_file.read(2)
                if len(length_bytes) != 2:
                    break
                length = struct.unpack(">H", length_bytes)[0]
                if length < 7:
                    break
                frame = uploaded_file.read(5)
                if len(frame) != 5:
                    break
                height, width = struct.unpack(">HH", frame[1:5])
                return width, height
            length_bytes = uploaded_file.read(2)
            if len(length_bytes) != 2:
                break
            length = struct.unpack(">H", length_bytes)[0]
            if length < 2:
                break
            uploaded_file.seek(length - 2, 1)

    return None


def _validate_signature(uploaded_file, content_type):
    header = uploaded_file.read(32)
    uploaded_file.seek(0)
    valid = {
        "image/png": header.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/gif": header[:6] in (b"GIF87a", b"GIF89a"),
        "image/jpeg": header[:2] == b"\xff\xd8",
        "image/webp": header[:4] == b"RIFF" and header[8:12] == b"WEBP",
        SUPPORTED_PDF_TYPE: header.startswith(b"%PDF-"),
    }
    if not valid.get(content_type, False):
        raise ValueError("The uploaded file content does not match its declared format.")


def _pdf_page_count(uploaded_file):
    data = uploaded_file.read()
    uploaded_file.seek(0)
    return len(re.findall(rb"/Type\s*/Page(?:\s|/|>)", data))


def file_metadata(uploaded_file):
    content_type = uploaded_file.content_type or ""
    suffix = Path(uploaded_file.name).suffix.lower()
    metadata = {
        "name": uploaded_file.name,
        "size_bytes": uploaded_file.size,
        "content_type": content_type,
        "extension": suffix,
        "sha256": _sha256(uploaded_file),
    }

    if content_type in SUPPORTED_IMAGE_TYPES:
        _validate_signature(uploaded_file, content_type)
        metadata["dimensions"] = _image_dimensions(uploaded_file, content_type)
    elif content_type == SUPPORTED_PDF_TYPE:
        _validate_signature(uploaded_file, content_type)
        metadata["page_count"] = PdfiumRenderer().inspect(uploaded_file.read())["page_count"]
        uploaded_file.seek(0)

    return metadata


def compare_uploads(first, second):
    if first.size > MAX_COMPARISON_FILE_SIZE or second.size > MAX_COMPARISON_FILE_SIZE:
        raise ValueError("Each comparison file must be 25 MB or smaller.")

    allowed = SUPPORTED_IMAGE_TYPES | {SUPPORTED_PDF_TYPE}
    if first.content_type not in allowed or second.content_type not in allowed:
        raise ValueError("Only PNG, JPEG, GIF, WEBP, and PDF files are supported.")

    first_metadata = file_metadata(first)
    second_metadata = file_metadata(second)
    same = first_metadata["sha256"] == second_metadata["sha256"]
    result = {
        "same_content": same,
        "same_type": first.content_type == second.content_type,
        "first": first_metadata,
        "second": second_metadata,
    }

    if first.content_type == second.content_type == SUPPORTED_PDF_TYPE:
        result["page_count_difference"] = (
            first_metadata["page_count"] - second_metadata["page_count"]
        )
        result["pdf_comparison"] = PdfiumRenderer().compare(
            first.read(), second.read()
        )
        first.seek(0)
        second.seek(0)
    if first.content_type == second.content_type and first.content_type in SUPPORTED_IMAGE_TYPES:
        result["same_dimensions"] = first_metadata.get("dimensions") == second_metadata.get(
            "dimensions"
        )

    return result
