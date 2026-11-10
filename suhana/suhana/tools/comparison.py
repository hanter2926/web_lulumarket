import hashlib
import json
import math
import struct
from pathlib import Path

from .pdf_rendering import IsolatedPdfRendererClient
from .image_comparison import (
    compare_image_pair_with_metadata,
    image_metadata,
)
from .rust_engine import ProcessingEngineError


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


def _invalid_engine_result():
    return ProcessingEngineError(
        "The Rust processing engine returned an invalid structured result."
    )


def _is_int_in_range(value, minimum, maximum):
    return type(value) is int and minimum <= value <= maximum


def _validate_image_metadata(metadata):
    if not isinstance(metadata, dict):
        raise _invalid_engine_result()
    dimensions = metadata.get("dimensions")
    if (
        not isinstance(dimensions, list)
        or len(dimensions) != 2
        or any(not _is_int_in_range(value, 1, 8192) for value in dimensions)
        or metadata.get("format") not in {"PNG", "JPEG", "GIF", "WEBP"}
        or type(metadata.get("animated")) is not bool
        or not _is_int_in_range(metadata.get("frame_count"), 1, 100)
        or type(metadata.get("has_alpha")) is not bool
    ):
        raise _invalid_engine_result()


def _validate_image_comparison(comparison, first, second):
    if not isinstance(comparison, dict):
        raise _invalid_engine_result()
    _validate_image_metadata(first)
    _validate_image_metadata(second)
    frame_results = comparison.get("frame_results")
    if (
        comparison.get("first_format") != first["format"]
        or comparison.get("second_format") != second["format"]
        or type(comparison.get("animated")) is not bool
        or not _is_int_in_range(
            comparison.get("frame_count_difference"), -99, 99
        )
        or not _is_int_in_range(comparison.get("visual_differences"), 0, 100)
        or type(comparison.get("same_visual")) is not bool
        or not isinstance(frame_results, list)
        or len(frame_results) != max(first["frame_count"], second["frame_count"])
    ):
        raise _invalid_engine_result()

    visual_differences = 0
    for index, frame in enumerate(frame_results, start=1):
        if not isinstance(frame, dict) or frame.get("frame") != index:
            raise _invalid_engine_result()
        status = frame.get("status")
        visual = frame.get("visual")
        if status in {"added", "removed"}:
            if visual is not None:
                raise _invalid_engine_result()
            visual_differences += 1
        elif status == "compared":
            if (
                not isinstance(visual, dict)
                or type(visual.get("same_dimensions")) is not bool
                or not isinstance(visual.get("difference_percentage"), (int, float))
                or not math.isfinite(visual["difference_percentage"])
                or not 0 <= visual["difference_percentage"] <= 100
            ):
                raise _invalid_engine_result()
            visual_differences += visual["difference_percentage"] > 0
        else:
            raise _invalid_engine_result()

    if (
        comparison["frame_count_difference"]
        != first["frame_count"] - second["frame_count"]
        or comparison["animated"]
        != (first["frame_count"] > 1 or second["frame_count"] > 1)
        or comparison["visual_differences"] != visual_differences
        or comparison["same_visual"] != (visual_differences == 0)
    ):
        raise _invalid_engine_result()


def _validate_pdf_comparison(comparison):
    if not isinstance(comparison, dict):
        raise _invalid_engine_result()
    first = comparison.get("first")
    second = comparison.get("second")
    page_results = comparison.get("page_results")
    if (
        not isinstance(first, dict)
        or not isinstance(second, dict)
        or not _is_int_in_range(first.get("page_count"), 0, 100)
        or not _is_int_in_range(second.get("page_count"), 0, 100)
        or type(first.get("has_text_layer")) is not bool
        or type(first.get("scanned_likely")) is not bool
        or type(second.get("has_text_layer")) is not bool
        or type(second.get("scanned_likely")) is not bool
        or not isinstance(page_results, list)
        or len(page_results) != max(first["page_count"], second["page_count"])
        or not _is_int_in_range(comparison.get("text_differences"), 0, 100)
        or not _is_int_in_range(comparison.get("visual_differences"), 0, 100)
    ):
        raise _invalid_engine_result()

    text_differences = 0
    visual_differences = 0
    for index, page in enumerate(page_results, start=1):
        if (
            not isinstance(page, dict)
            or page.get("page") != index
            or type(page.get("text_same")) is not bool
        ):
            raise _invalid_engine_result()
        text_differences += not page["text_same"]
        visual = page.get("visual")
        if visual is not None:
            if (
                not isinstance(visual, dict)
                or type(visual.get("same_dimensions")) is not bool
                or not isinstance(visual.get("difference_percentage"), (int, float))
                or not math.isfinite(visual["difference_percentage"])
                or not 0 <= visual["difference_percentage"] <= 100
            ):
                raise _invalid_engine_result()
            visual_differences += visual["difference_percentage"] > 0

    if (
        comparison["text_differences"] != text_differences
        or comparison["visual_differences"] != visual_differences
    ):
        raise _invalid_engine_result()


def _validate_comparison_result(result, first, second):
    if not isinstance(result, dict):
        raise _invalid_engine_result()
    first_metadata = result.get("first")
    second_metadata = result.get("second")
    for upload, metadata in (
        (first, first_metadata),
        (second, second_metadata),
    ):
        digest = metadata.get("sha256") if isinstance(metadata, dict) else None
        if (
            not isinstance(metadata, dict)
            or metadata.get("name") != upload.name
            or metadata.get("size_bytes") != upload.size
            or metadata.get("content_type") != upload.content_type
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise _invalid_engine_result()

    if (
        type(result.get("same_content")) is not bool
        or type(result.get("same_type")) is not bool
        or result["same_content"] != (first_metadata["sha256"] == second_metadata["sha256"])
        or result["same_type"] != (first.content_type == second.content_type)
    ):
        raise _invalid_engine_result()

    if first.content_type in SUPPORTED_IMAGE_TYPES and second.content_type in SUPPORTED_IMAGE_TYPES:
        image_result = result.get("image_comparison")
        _validate_image_comparison(image_result, first_metadata, second_metadata)
    if first.content_type == second.content_type == SUPPORTED_PDF_TYPE:
        pdf_result = result.get("pdf_comparison")
        _validate_pdf_comparison(pdf_result)
        if (
            first_metadata.get("page_count") != pdf_result["first"]["page_count"]
            or second_metadata.get("page_count") != pdf_result["second"]["page_count"]
        ):
            raise _invalid_engine_result()

    try:
        json.dumps(result, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise _invalid_engine_result() from error
    return result


def file_metadata(
    uploaded_file,
    image_metadata_override=None,
    pdf_page_count_override=None,
):
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
        if image_metadata_override is None:
            image_data = uploaded_file.read()
            uploaded_file.seek(0)
            image_metadata_override = image_metadata(image_data)
        metadata.update(image_metadata_override)
    elif content_type == SUPPORTED_PDF_TYPE:
        _validate_signature(uploaded_file, content_type)
        if pdf_page_count_override is None:
            page_count = IsolatedPdfRendererClient().inspect(
                uploaded_file.read()
            )["page_count"]
        else:
            page_count = pdf_page_count_override
        metadata["page_count"] = page_count
        uploaded_file.seek(0)

    return metadata


def compare_uploads(first, second):
    if first.size > MAX_COMPARISON_FILE_SIZE or second.size > MAX_COMPARISON_FILE_SIZE:
        raise ValueError("Each comparison file must be 25 MB or smaller.")

    allowed = SUPPORTED_IMAGE_TYPES | {SUPPORTED_PDF_TYPE}
    if first.content_type not in allowed or second.content_type not in allowed:
        raise ValueError("Only PNG, JPEG, GIF, WEBP, and PDF files are supported.")

    _validate_signature(first, first.content_type)
    _validate_signature(second, second.content_type)
    image_comparison = None
    first_image_metadata = None
    second_image_metadata = None
    pdf_comparison = None
    if first.content_type in SUPPORTED_IMAGE_TYPES and second.content_type in SUPPORTED_IMAGE_TYPES:
        first_image_data = first.read()
        second_image_data = second.read()
        first.seek(0)
        second.seek(0)
        (
            image_comparison,
            first_image_metadata,
            second_image_metadata,
        ) = compare_image_pair_with_metadata(first_image_data, second_image_data)
    if first.content_type == second.content_type == SUPPORTED_PDF_TYPE:
        pdf_comparison = IsolatedPdfRendererClient().compare(
            first.read(), second.read()
        )
        _validate_pdf_comparison(pdf_comparison)
        first.seek(0)
        second.seek(0)

    first_pdf_page_count = (
        pdf_comparison["first"]["page_count"] if pdf_comparison is not None else None
    )
    second_pdf_page_count = (
        pdf_comparison["second"]["page_count"] if pdf_comparison is not None else None
    )
    first_metadata = file_metadata(
        first,
        first_image_metadata,
        first_pdf_page_count,
    )
    second_metadata = file_metadata(
        second,
        second_image_metadata,
        second_pdf_page_count,
    )
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
        result["pdf_comparison"] = pdf_comparison
    if first.content_type in SUPPORTED_IMAGE_TYPES and second.content_type in SUPPORTED_IMAGE_TYPES:
        result["same_dimensions"] = first_metadata.get("dimensions") == second_metadata.get(
            "dimensions"
        )
        result["image_comparison"] = image_comparison

    return _validate_comparison_result(result, first, second)
