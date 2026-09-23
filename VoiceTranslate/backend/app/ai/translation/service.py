"""Translation service interface."""

from dataclasses import dataclass
from typing import Any

from app.ai.translation.loader import TranslationModelLoader, get_shared_translation_loader
from app.config import Settings
from app.utils.constants import normalize_language_code


class TranslationError(RuntimeError):
	"""Raised when translation cannot be completed safely."""


@dataclass(frozen=True)
class Translation:
	source_text: str
	translated_text: str
	source_language: str
	target_language: str

	def to_dict(self) -> dict[str, str]:
		return {
			"source_text": self.source_text,
			"translated_text": self.translated_text,
			"source_language": self.source_language,
			"target_language": self.target_language,
		}


class SeamlessTranslationService:
	def __init__(self, settings: Settings, loader: TranslationModelLoader | None = None) -> None:
		self.settings = settings
		self.loader = loader or get_shared_translation_loader(settings)

	def translate(
		self,
		text: str,
		source_language: str | None = None,
		target_language: str | None = None,
	) -> Translation:
		if not text or not text.strip():
			raise TranslationError("Translation text is empty")
		try:
			source = normalize_language_code(source_language or self.settings.translation_source_language)
			target = normalize_language_code(target_language or self.settings.translation_target_language)
			model, processor = self.loader.load()
			inputs = processor(text=text.strip(), src_lang=source, return_tensors="pt")
			if self.settings.translation_device != "cpu":
				inputs = {
					key: value.to(self.settings.translation_device) if hasattr(value, "to") else value
					for key, value in inputs.items()
				}
			output = model.generate(**inputs, tgt_lang=target, generate_speech=False)
			decoded_tokens = output[0].tolist()
			if decoded_tokens and isinstance(decoded_tokens[0], list):
				decoded_tokens = decoded_tokens[0]
			translated = str(processor.decode(decoded_tokens, skip_special_tokens=True)).strip()
			return Translation(text.strip(), translated, source, target)
		except TranslationError:
			raise
		except ValueError as exc:
			raise TranslationError("Unsupported language") from exc
		except Exception as exc:
			raise TranslationError("Translation failed") from exc
