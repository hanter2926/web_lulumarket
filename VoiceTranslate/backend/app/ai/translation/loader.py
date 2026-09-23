"""SeamlessM4T model lifecycle management."""

from collections.abc import Callable
from threading import Lock
from typing import Any

from app.config import Settings


_shared_loaders: dict[tuple[str, str, str], "TranslationModelLoader"] = {}
_shared_loaders_lock = Lock()


class TranslationModelLoader:
	"""Lazily load and cache one SeamlessM4T model and processor."""

	def __init__(
		self,
		settings: Settings,
		model_factory: Callable[..., Any] | None = None,
		processor_factory: Callable[..., Any] | None = None,
	) -> None:
		self.settings = settings
		self._model_factory = model_factory
		self._processor_factory = processor_factory
		self._loaded: tuple[Any, Any] | None = None
		self._lock = Lock()

	def load(self) -> tuple[Any, Any]:
		if self._loaded is None:
			with self._lock:
				if self._loaded is None:
					model_factory = self._model_factory
					processor_factory = self._processor_factory
					if model_factory is None or processor_factory is None:
						from transformers import AutoProcessor, SeamlessM4Tv2Model

						model_factory = model_factory or SeamlessM4Tv2Model.from_pretrained
						processor_factory = processor_factory or AutoProcessor.from_pretrained
					processor = processor_factory(self.settings.translation_model)
					model = model_factory(self.settings.translation_model)
					if self.settings.translation_device != "cpu":
						model = model.to(self.settings.translation_device)
					self._loaded = (model, processor)
		return self._loaded


def get_shared_translation_loader(settings: Settings) -> TranslationModelLoader:
	key = (settings.translation_model, settings.translation_device, settings.translation_compute_type)
	with _shared_loaders_lock:
		loader = _shared_loaders.get(key)
		if loader is None:
			loader = TranslationModelLoader(settings)
			_shared_loaders[key] = loader
		return loader
