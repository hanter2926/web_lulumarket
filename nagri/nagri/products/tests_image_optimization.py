import io
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nagri.settings")

import django

django.setup()

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.db.models import ImageField
from django.test import override_settings
from PIL import Image, ImageSequence
from PIL.TiffImagePlugin import IFDRational

from nagri.image_optimization import (
    MAX_INPUT_DIMENSION,
    MAX_INPUT_PIXELS,
    POLICIES,
    optimize_image,
    policy_for_path,
)
from nagri.optimized_storage import OptimizedImageStorage


class RecordingStorage(Storage):
    def __init__(self):
        self.saved = []
        self.existing_names = set()

    def _save(self, name, content):
        content.seek(0)
        self.saved.append((name, content.read()))
        return name

    def delete(self, name):
        return None

    def exists(self, name):
        return name in self.existing_names

    def listdir(self, path):
        return [], []

    def path(self, name):
        return name

    def size(self, name):
        return 0

    def url(self, name):
        return f"https://storage.example/{name}"

    def _open(self, name, mode="rb"):
        return io.BytesIO()


class FakeCloudinaryStorage(RecordingStorage):
    pass


class FakeFileSystemStorage(RecordingStorage):
    pass


def make_image_bytes(image_format, size=(100, 60), mode="RGB", color=None, **options):
    if color is None:
        color = (40, 100, 180, 90) if "A" in mode else (40, 100, 180)
    image = Image.new(mode, size, color)
    output = io.BytesIO()
    image.save(output, format=image_format, **options)
    image.close()
    return output.getvalue()


class ImageProcessingTests(unittest.TestCase):
    def test_jpeg_is_reencoded_at_same_format_and_within_size_limit(self):
        data = make_image_bytes("JPEG", size=(2200, 1100))
        uploaded_file = ContentFile(data)
        uploaded_file.seek(7)
        result = optimize_image("products/item.jpg", uploaded_file)
        try:
            self.assertEqual(uploaded_file.tell(), 7)
            with Image.open(result) as image:
                self.assertEqual(image.format, "JPEG")
                self.assertLessEqual(max(image.size), 1600)
                self.assertAlmostEqual(image.width / image.height, 2, places=2)
        finally:
            result.close()

    def test_png_icc_profile_is_preserved(self):
        profile = b"test color profile"
        data = make_image_bytes("PNG", icc_profile=profile)
        result = optimize_image(
            "categories/profiled.png",
            ContentFile(data),
        )
        try:
            with Image.open(result) as image:
                self.assertEqual(image.info.get("icc_profile"), profile)
        finally:
            result.close()

    def test_png_alpha_is_preserved(self):
        data = make_image_bytes("PNG", mode="RGBA")
        result = optimize_image("categories/category.png", ContentFile(data))
        try:
            with Image.open(result) as image:
                self.assertEqual(image.format, "PNG")
                self.assertIn("A", image.getbands())
                self.assertEqual(image.getpixel((0, 0))[3], 90)
        finally:
            result.close()

    def test_gif_transparency_is_preserved(self):
        image = Image.new("P", (20, 20), 0)
        image.putpalette([0, 0, 0, 255, 0, 0] + [0, 0, 0] * 254)
        image.putpixel((10, 10), 1)
        source = io.BytesIO()
        image.save(source, format="GIF", transparency=0)
        image.close()

        result = optimize_image(
            "categories/transparent.gif",
            ContentFile(source.getvalue()),
        )
        try:
            with Image.open(result) as output:
                rgba = output.convert("RGBA")
                self.assertEqual(rgba.getpixel((0, 0))[3], 0)
                self.assertEqual(rgba.getpixel((10, 10))[3], 255)
        finally:
            result.close()

    def test_webp_alpha_is_preserved(self):
        data = make_image_bytes("WEBP", mode="RGBA", lossless=True)
        result = optimize_image("products/gallery.webp", ContentFile(data))
        try:
            with Image.open(result) as image:
                self.assertEqual(image.format, "WEBP")
                self.assertIn("A", image.getbands())
                self.assertGreaterEqual(image.getpixel((0, 0))[3], 89)
        finally:
            result.close()

    def test_exif_orientation_is_applied_and_metadata_removed(self):
        image = Image.new("RGB", (40, 20), "red")
        exif = Image.Exif()
        exif[274] = 6
        exif[37510] = b"private metadata"
        gps_ifd = exif.get_ifd(34853)
        gps_ifd[1] = "N"
        gps_ifd[2] = (
            IFDRational(37, 1),
            IFDRational(0, 1),
            IFDRational(0, 1),
        )
        source = io.BytesIO()
        image.save(source, format="JPEG", exif=exif)
        image.close()

        result = optimize_image(
            "products/oriented.jpg",
            ContentFile(source.getvalue()),
        )
        try:
            with Image.open(result) as output:
                self.assertEqual(output.size, (20, 40))
                self.assertNotIn("exif", output.info)
                self.assertNotIn("gps", output.getexif())
                self.assertNotIn(34853, output.getexif())
        finally:
            result.close()

    def test_animated_gif_keeps_frames_timing_and_loop(self):
        frames = [
            Image.new("RGBA", (40, 30), (255, 0, 0, 255)),
            Image.new("RGBA", (40, 30), (0, 0, 255, 255)),
        ]
        source = io.BytesIO()
        frames[0].save(
            source,
            format="GIF",
            save_all=True,
            append_images=frames[1:],
            duration=[80, 140],
            loop=3,
            disposal=[2, 1],
        )
        for frame in frames:
            frame.close()

        result = optimize_image(
            "sliders/animated.gif",
            ContentFile(source.getvalue()),
        )
        try:
            with Image.open(result) as output:
                self.assertEqual(output.format, "GIF")
                self.assertEqual(output.n_frames, 2)
                self.assertEqual(output.info.get("loop"), 3)
                durations = [
                    frame.info.get("duration")
                    for frame in ImageSequence.Iterator(output)
                ]
                disposals = [
                    frame.disposal_method
                    for frame in ImageSequence.Iterator(output)
                ]
                self.assertEqual(durations, [80, 140])
                self.assertEqual(disposals, [2, 1])
        finally:
            result.close()

    def test_animated_webp_is_rejected_instead_of_losing_animation(self):
        frames = [
            Image.new("RGBA", (40, 30), (255, 0, 0, 255)),
            Image.new("RGBA", (40, 30), (0, 0, 255, 90)),
        ]
        source = io.BytesIO()
        frames[0].save(
            source,
            format="WEBP",
            save_all=True,
            append_images=frames[1:],
            duration=[80, 140],
            loop=2,
            lossless=True,
        )
        for frame in frames:
            frame.close()

        with self.assertRaises(ValidationError):
            optimize_image(
                "products/animated.webp",
                ContentFile(source.getvalue()),
            )

    def test_mismatched_truncated_empty_and_unsupported_files_are_rejected(self):
        valid_png = make_image_bytes("PNG")
        cases = (
            ("products/mismatch.jpg", valid_png),
            ("products/truncated.png", valid_png[:20]),
            ("products/empty.png", b""),
            ("products/unsupported.svg", b"<svg></svg>"),
        )
        for name, data in cases:
            with self.subTest(name=name), self.assertRaises(ValidationError):
                optimize_image(name, ContentFile(data))

    def test_byte_size_limit_is_enforced(self):
        with patch(
            "nagri.image_optimization.POLICIES",
            {
                **POLICIES,
                "products": POLICIES["categories"],
            },
        ):
            oversized = b"x" * (5 * 1024 * 1024 + 1)
            with self.assertRaises(ValidationError):
                optimize_image("products/large.png", ContentFile(oversized))

    def test_dimension_and_pixel_limits_are_enforced(self):
        too_wide = make_image_bytes(
            "PNG",
            size=(MAX_INPUT_DIMENSION + 1, 1),
        )
        too_many_pixels = make_image_bytes(
            "PNG",
            size=(7000, 6000),
        )
        for data in (too_wide, too_many_pixels):
            with self.assertRaises(ValidationError):
                optimize_image("products/too-large.png", ContentFile(data))
        self.assertEqual(MAX_INPUT_PIXELS, 40_000_000)

    def test_unapproved_file_path_is_not_processed(self):
        self.assertEqual(policy_for_path("seller_documents/id.png"), None)


class StorageTests(unittest.TestCase):
    def test_selected_cloudinary_backend_is_delegated_to_once(self):
        backend_path = (
            "products.tests_image_optimization.FakeCloudinaryStorage"
        )
        with override_settings(IMAGE_OPTIMIZATION_BASE_STORAGE=backend_path):
            storage = OptimizedImageStorage()
            self.assertIsInstance(storage._base_storage, FakeCloudinaryStorage)
            with patch(
                "nagri.optimized_storage.optimize_image",
                wraps=optimize_image,
            ) as process_image:
                name = storage.save(
                    "categories/item.png",
                    ContentFile(make_image_bytes("PNG")),
                )
            process_image.assert_called_once()

        self.assertEqual(name, "categories/item.png")
        self.assertEqual(len(storage._base_storage.saved), 1)
        self.assertEqual(storage.url(name), f"https://storage.example/{name}")

    def test_selected_local_backend_is_delegated_to_once(self):
        backend_path = (
            "products.tests_image_optimization.FakeFileSystemStorage"
        )
        with override_settings(IMAGE_OPTIMIZATION_BASE_STORAGE=backend_path):
            storage = OptimizedImageStorage()
            self.assertIsInstance(storage._base_storage, FakeFileSystemStorage)
            name = storage.save(
                "products/item.webp",
                ContentFile(make_image_bytes("WEBP")),
            )

        self.assertEqual(name, "products/item.webp")
        self.assertEqual(len(storage._base_storage.saved), 1)

    def test_unapproved_filefield_is_passed_through_unmodified(self):
        backend = RecordingStorage()
        storage = OptimizedImageStorage(base_storage=backend)
        content = ContentFile(b"receipt content")
        name = storage.save("upi_receipts/receipt.jpg", content)

        self.assertEqual(name, "upi_receipts/receipt.jpg")
        self.assertEqual(backend.saved, [(name, b"receipt content")])

    def test_storage_naming_policy_is_delegated_to_backend(self):
        backend = RecordingStorage()
        with patch.object(
            backend,
            "get_available_name",
            return_value="backend-selected-name.png",
        ) as get_available_name:
            storage = OptimizedImageStorage(base_storage=backend)
            self.assertEqual(
                storage.get_available_name("categories/item.png"),
                "backend-selected-name.png",
            )
        get_available_name.assert_called_once_with(
            "categories/item.png",
            max_length=None,
        )


class ImageFieldCoverageTests(unittest.TestCase):
    def test_all_approved_image_fields_have_allowlisted_upload_paths(self):
        from accounts.models import CustomUser, HomeSlider as AccountHomeSlider
        from accounts.models import UserProfile
        from products.models import Category, Product, ProductImage
        from unyan.models import HomeSlider as UnyanHomeSlider

        expected = {
            (Category, "image"): "categories/",
            (Product, "image"): "products/",
            (ProductImage, "image"): "products/",
            (CustomUser, "avatar"): "profiles/",
            (UserProfile, "avatar"): "profiles/",
            (AccountHomeSlider, "image"): "sliders/",
            (AccountHomeSlider, "mobile_image"): "sliders/mobile/",
            (UnyanHomeSlider, "image"): "sliders/",
            (UnyanHomeSlider, "mobile_image"): "sliders/",
        }
        self.assertEqual(len(expected), 9)
        for (model, field_name), upload_path in expected.items():
            with self.subTest(model=model.__name__, field=field_name):
                field = model._meta.get_field(field_name)
                self.assertIsInstance(field, ImageField)
                self.assertEqual(field.upload_to, upload_path)
                self.assertIsNotNone(policy_for_path(upload_path + "test.png"))
                self.assertIsInstance(field.storage, OptimizedImageStorage)

    def test_default_and_base_storage_are_different_to_prevent_recursion(self):
        self.assertEqual(
            settings.STORAGES["default"]["BACKEND"],
            "nagri.optimized_storage.OptimizedImageStorage",
        )
        self.assertNotEqual(
            settings.IMAGE_OPTIMIZATION_BASE_STORAGE,
            settings.STORAGES["default"]["BACKEND"],
        )
