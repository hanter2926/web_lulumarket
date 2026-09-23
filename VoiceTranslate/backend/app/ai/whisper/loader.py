"""Faster-Whisper model lifecycle management."""

from collections.abc import Callable
from threading import Lock
from typing import Any

from app.config import Settings


_shared_loaders: dict[tuple[str, str, str], "WhisperModelLoader"] = {}
_shared_loaders_lock = Lock()


class WhisperModelLoader:
	"""Lazily construct one configured Faster-Whisper model per service."""

	def __init__(self, settings: Settings, model_factory: Callable[..., Any] | None = None) -> None:
		self.settings = settings
		self._model_factory = model_factory
		self._model: Any | None = None
		self._lock = Lock()

	def load(self) -> Any:
		if self._model is None:
			with self._lock:
				if self._model is None:
					factory = self._model_factory
					if factory is None:
						from faster_whisper import WhisperModel

						factory = WhisperModel
					self._model = factory(
						self.settings.whisper_model_size,
						device=self.settings.whisper_device,
						compute_type=self.settings.whisper_compute_type,
					)
		return self._model


def get_shared_whisper_model_loader(settings: Settings) -> WhisperModelLoader:
	key = (settings.whisper_model_size, settings.whisper_device, settings.whisper_compute_type)
	with _shared_loaders_lock:
		loader = _shared_loaders.get(key)
		if loader is None:
			loader = WhisperModelLoader(settings)
			_shared_loaders[key] = loader
		return loader
