import base64
import io
import struct

from PIL import Image, ImageFile, ImageSequence, UnidentifiedImageError


MAX_IMAGE_DIMENSION = 8_192
MAX_IMAGE_PIXELS = 80_000_000
MAX_ANIMATED_FRAMES = 100
MAX_PREVIEW_BYTES = 1_000_000

ImageFile.LOAD_TRUNCATED_IMAGES = False


def _normalise_rgba(image):
    rgba = bytearray(image.convert("RGBA").tobytes())
    for index in range(0, len(rgba), 4):
        if rgba[index + 3] == 0:
            rgba[index] = rgba[index + 1] = rgba[index + 2] = 0
    return bytes(rgba)


def _open_image(data):
    try:
        image = Image.open(io.BytesIO(data))
        image.verify()
        image = Image.open(io.BytesIO(data))
    except (OSError, ValueError, UnidentifiedImageError) as error:
        raise ValueError("The uploaded image is malformed or unsupported.") from error

    width, height = image.size
    if (
        width <= 0
        or height <= 0
        or width > MAX_IMAGE_DIMENSION
        or height > MAX_IMAGE_DIMENSION
        or width * height > MAX_IMAGE_PIXELS
    ):
        image.close()
        raise ValueError("The image dimensions exceed the supported safety limits.")
    return image


def _frames(data):
    image = _open_image(data)
    try:
        frame_count = getattr(image, "n_frames", 1)
        if frame_count > MAX_ANIMATED_FRAMES:
            raise ValueError("Animated images may contain at most 100 frames.")
        frames = []
        for frame in ImageSequence.Iterator(image):
            frames.append((frame.size, _normalise_rgba(frame.copy())))
        return image.format, frames
    finally:
        image.close()


def image_metadata(data):
    image = _open_image(data)
    try:
        return {
            "dimensions": list(image.size),
            "format": image.format,
            "animated": getattr(image, "n_frames", 1) > 1,
            "frame_count": getattr(image, "n_frames", 1),
            "has_alpha": "A" in image.getbands() or "transparency" in image.info,
        }
    finally:
        image.close()


def _overlay_data_url(width, height, changed):
    overlay = Image.new("RGBA", (width, height))
    pixels = overlay.load()
    for index, value in enumerate(changed):
        if value:
            pixels[index % width, index // width] = (255, 0, 0, 180)
    output = io.BytesIO()
    overlay.save(output, format="PNG", optimize=True)
    encoded = output.getvalue()
    if len(encoded) > MAX_PREVIEW_BYTES:
        return None
    return "data:image/png;base64," + base64.b64encode(encoded).decode("ascii")


def _compare_frame(first, second):
    (first_width, first_height), first_pixels = first
    (second_width, second_height), second_pixels = second
    if (first_width, first_height) != (second_width, second_height):
        return {
            "same_dimensions": False,
            "differing_pixels": None,
            "difference_percentage": 100.0,
            "overlay_png": None,
        }

    changed = []
    differing = 0
    for index in range(0, len(first_pixels), 4):
        different = first_pixels[index : index + 4] != second_pixels[index : index + 4]
        changed.append(different)
        differing += different
    total = first_width * first_height
    return {
        "same_dimensions": True,
        "differing_pixels": differing,
        "difference_percentage": round(differing * 100 / total, 6),
        "overlay_png": _overlay_data_url(first_width, first_height, changed),
    }


def compare_images(first_data, second_data):
    first_format, first_frames = _frames(first_data)
    second_format, second_frames = _frames(second_data)
    frame_results = []
    for index in range(max(len(first_frames), len(second_frames))):
        if index >= len(first_frames):
            frame_results.append({"frame": index + 1, "status": "added", "visual": None})
        elif index >= len(second_frames):
            frame_results.append({"frame": index + 1, "status": "removed", "visual": None})
        else:
            frame_results.append(
                {
                    "frame": index + 1,
                    "status": "compared",
                    "visual": _compare_frame(first_frames[index], second_frames[index]),
                }
            )

    visual_differences = sum(
        1
        for result in frame_results
        if result["visual"] is None
        or result["visual"]["difference_percentage"] > 0
    )
    return {
        "first_format": first_format,
        "second_format": second_format,
        "animated": len(first_frames) > 1 or len(second_frames) > 1,
        "frame_count_difference": len(first_frames) - len(second_frames),
        "frame_results": frame_results,
        "visual_differences": visual_differences,
        "same_visual": visual_differences == 0,
    }
