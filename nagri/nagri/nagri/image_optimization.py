import os
import tempfile
import warnings
from dataclasses import dataclass
from pathlib import PurePosixPath

from django.core.exceptions import ValidationError
from django.core.files.utils import validate_file_name
from PIL import Image, ImageOps, ImageSequence, UnidentifiedImageError


MIB = 1024 * 1024
MAX_INPUT_DIMENSION = 8000
MAX_INPUT_PIXELS = 40_000_000
MAX_ANIMATION_FRAMES = 300


@dataclass(frozen=True)
class ImagePolicy:
    max_bytes: int
    max_dimensions: tuple[int, int]
    quality: int


POLICIES = {
    "categories": ImagePolicy(5 * MIB, (600, 600), 82),
    "products": ImagePolicy(10 * MIB, (1600, 1600), 85),
    "profiles": ImagePolicy(5 * MIB, (512, 512), 82),
    "sliders/mobile": ImagePolicy(15 * MIB, (600, 400), 88),
    # unyan.HomeSlider.mobile_image shares this path with desktop banners.
    "sliders": ImagePolicy(15 * MIB, (600, 400), 88),
}

EXTENSION_FORMATS = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
    ".webp": "WEBP",
    ".gif": "GIF",
}

PIL_FORMATS = {
    "JPEG": "JPEG",
    "PNG": "PNG",
    "WEBP": "WEBP",
    "GIF": "GIF",
}


def policy_for_path(name):
    normalized_name = name.replace("\\", "/")
    parts = PurePosixPath(normalized_name).parts
    if not parts or parts[0] in ("", ".", ".."):
        return None

    for prefix in sorted(POLICIES, key=len, reverse=True):
        prefix_parts = tuple(prefix.split("/"))
        if parts[: len(prefix_parts)] == prefix_parts:
            return POLICIES[prefix]
    return None


def _read_upload_to_spool(content, max_bytes):
    spool = tempfile.SpooledTemporaryFile(max_size=1024 * 1024, mode="w+b")
    original_position = None
    try:
        if hasattr(content, "tell") and hasattr(content, "seek"):
            try:
                original_position = content.tell()
                content.seek(0)
            except (OSError, ValueError):
                original_position = None

        total_size = 0
        if hasattr(content, "chunks"):
            chunks = content.chunks()
        else:
            def read_chunks():
                while True:
                    chunk = content.read(64 * 1024)
                    if not chunk:
                        break
                    yield chunk

            chunks = read_chunks()

        for chunk in chunks:
            total_size += len(chunk)
            if total_size > max_bytes:
                raise ValidationError(
                    f"Image uploads must not exceed {max_bytes // MIB} MiB."
                )
            spool.write(chunk)
        if not total_size:
            raise ValidationError("The uploaded image is empty.")
        spool.seek(0)
        return spool
    except Exception:
        spool.close()
        raise
    finally:
        if original_position is not None:
            try:
                content.seek(original_position)
            except (OSError, ValueError):
                pass


def _validate_image(spool, name, policy):
    extension = os.path.splitext(name)[1].lower()
    expected_format = EXTENSION_FORMATS.get(extension)
    if expected_format is None:
        raise ValidationError("Unsupported image file extension.")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            spool.seek(0)
            with Image.open(spool) as image:
                image_format = image.format
                if image_format not in PIL_FORMATS:
                    raise ValidationError("Unsupported image format.")
                if image_format != expected_format:
                    raise ValidationError(
                        "The image contents do not match the file extension."
                    )
                if image.width > MAX_INPUT_DIMENSION or image.height > MAX_INPUT_DIMENSION:
                    raise ValidationError(
                        f"Image dimensions must not exceed {MAX_INPUT_DIMENSION} pixels."
                    )
                if image.width * image.height > MAX_INPUT_PIXELS:
                    raise ValidationError(
                        "Image pixel count must not exceed 40 megapixels."
                    )
                frame_count = getattr(image, "n_frames", 1)
                if frame_count > MAX_ANIMATION_FRAMES:
                    raise ValidationError(
                        f"Animated images must not exceed {MAX_ANIMATION_FRAMES} frames."
                    )
                if image.width * image.height * frame_count > MAX_INPUT_PIXELS:
                    raise ValidationError(
                        "Animated image pixel count must not exceed 40 megapixels."
                    )
                if frame_count > 1 and image_format != "GIF":
                    raise ValidationError(
                        "Only animated GIF images are supported."
                    )
                image.verify()

            spool.seek(0)
            with Image.open(spool) as image:
                image.load()
                if image.format != expected_format:
                    raise ValidationError(
                        "The image contents do not match the file extension."
                    )
                return image_format, image.info.copy(), getattr(image, "n_frames", 1)
    except ValidationError:
        raise
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
        UnidentifiedImageError,
        SyntaxError,
        ValueError,
    ) as exc:
        raise ValidationError("The uploaded image is invalid or damaged.") from exc


def _resize(image, dimensions):
    image.thumbnail(
        dimensions,
        Image.Resampling.LANCZOS,
        reducing_gap=3.0,
    )
    return image


def _save_still_image(image, destination, image_format, policy, info):
    image = ImageOps.exif_transpose(image)
    _resize(image, policy.max_dimensions)
    options = {}
    icc_profile = info.get("icc_profile")
    if icc_profile:
        options["icc_profile"] = icc_profile

    if image_format == "JPEG":
        if image.mode not in ("L", "RGB", "CMYK"):
            image = image.convert("RGB")
        options.update(
            quality=policy.quality,
            optimize=True,
            progressive=True,
        )
    elif image_format == "PNG":
        options.update(optimize=True, compress_level=9)
    elif image_format == "WEBP":
        if image.mode not in ("RGB", "RGBA", "L", "LA"):
            image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
        options.update(
            quality=policy.quality,
            alpha_quality=100,
            method=6,
        )
    elif image_format == "GIF":
        options["optimize"] = True
        if "transparency" in info:
            options["transparency"] = info["transparency"]
    image.save(destination, format=image_format, **options)


def _save_animated_gif(image, destination, policy, info):
    frames = []
    durations = []
    disposals = []
    try:
        for frame in ImageSequence.Iterator(image):
            disposal = getattr(frame, "disposal_method", info.get("disposal", 0))
            frame = frame.copy()
            _resize(frame, policy.max_dimensions)
            frames.append(frame)
            durations.append(frame.info.get("duration", info.get("duration", 0)))
            disposals.append(disposal)

        first_frame = frames[0].convert("RGBA")
        try:
            all_frames_identical = True
            for frame in frames[1:]:
                rgba_frame = frame.convert("RGBA")
                try:
                    if rgba_frame.tobytes() != first_frame.tobytes():
                        all_frames_identical = False
                        break
                finally:
                    rgba_frame.close()
        finally:
            first_frame.close()

        options = {
            "format": "GIF",
            "save_all": True,
            "append_images": frames[1:],
            "duration": durations,
            "disposal": (
                disposals[0]
                if all_frames_identical or not disposals
                else disposals
            ),
            "optimize": True,
        }
        for key in ("loop", "transparency", "background"):
            if key in info:
                options[key] = info[key]
        frames[0].save(destination, **options)
    finally:
        for frame in frames:
            frame.close()


def optimize_image(name, content):
    validate_file_name(name, allow_relative_path=True)
    policy = policy_for_path(name)
    if policy is None:
        raise ValueError("No image optimization policy exists for this path.")

    source = _read_upload_to_spool(content, policy.max_bytes)
    optimized = tempfile.SpooledTemporaryFile(max_size=1024 * 1024, mode="w+b")
    try:
        image_format, info, frame_count = _validate_image(source, name, policy)
        source.seek(0)
        with Image.open(source) as image:
            if image_format == "GIF" and frame_count > 1:
                _save_animated_gif(image, optimized, policy, info)
            else:
                image.load()
                _save_still_image(image, optimized, image_format, policy, info)
        optimized.seek(0)
        return optimized
    except Exception:
        optimized.close()
        raise
    finally:
        source.close()
