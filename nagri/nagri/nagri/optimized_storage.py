from importlib import import_module

from django.conf import settings
from django.core.files.storage import Storage
from django.core.files.utils import validate_file_name

from .image_optimization import optimize_image, policy_for_path


def _load_storage_backend(backend_path):
    module_path, class_name = backend_path.rsplit(".", 1)
    backend_class = getattr(import_module(module_path), class_name)
    return backend_class()


class OptimizedImageStorage(Storage):
    def __init__(self, base_storage=None):
        self._base_storage = base_storage or _load_storage_backend(
            settings.IMAGE_OPTIMIZATION_BASE_STORAGE
        )

    def save(self, name, content, max_length=None):
        if name is None:
            name = content.name
        validate_file_name(name, allow_relative_path=True)

        if policy_for_path(name) is None:
            return self._base_storage.save(name, content, max_length=max_length)

        optimized = optimize_image(name, content)
        try:
            return self._base_storage.save(
                name,
                optimized,
                max_length=max_length,
            )
        finally:
            optimized.close()

    def _save(self, name, content):
        return self._base_storage._save(name, content)

    def delete(self, name):
        return self._base_storage.delete(name)

    def exists(self, name):
        return self._base_storage.exists(name)

    def listdir(self, path):
        return self._base_storage.listdir(path)

    def path(self, name):
        return self._base_storage.path(name)

    def size(self, name):
        return self._base_storage.size(name)

    def url(self, name):
        return self._base_storage.url(name)

    def open(self, name, mode="rb"):
        return self._base_storage.open(name, mode)

    def get_accessed_time(self, name):
        return self._base_storage.get_accessed_time(name)

    def get_created_time(self, name):
        return self._base_storage.get_created_time(name)

    def get_modified_time(self, name):
        return self._base_storage.get_modified_time(name)

    def get_available_name(self, name, max_length=None):
        return self._base_storage.get_available_name(name, max_length=max_length)

    def get_valid_name(self, name):
        return self._base_storage.get_valid_name(name)

    def generate_filename(self, filename):
        return self._base_storage.generate_filename(filename)

    def __getattr__(self, name):
        return getattr(self._base_storage, name)
