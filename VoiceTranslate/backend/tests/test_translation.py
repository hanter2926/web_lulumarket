from dataclasses import dataclass

import pytest

from app.ai.translation.loader import TranslationModelLoader
from app.ai.translation.service import SeamlessTranslationService, TranslationError
from app.config import Settings


@dataclass
class FakeTensor:
	def __getitem__(self, index):
		return self

	def tolist(self):
		return [[1, 2, 3]]


class FakeProcessor:
	def __init__(self) -> None:
		self.calls: list[dict] = []

	def __call__(self, *, text, src_lang, return_tensors):
		self.calls.append({"text": text, "src_lang": src_lang, "return_tensors": return_tensors})
		return {"input_ids": FakeTensor()}

	def decode(self, tokens, *, skip_special_tokens):
		assert tokens == [1, 2, 3]
		assert skip_special_tokens is True
		return "Bonjour"


class FakeModel:
	def __init__(self) -> None:
		self.calls: list[dict] = []

	def generate(self, *, input_ids, tgt_lang, generate_speech):
		self.calls.append({"input_ids": input_ids, "tgt_lang": tgt_lang, "generate_speech": generate_speech})
		return FakeTensor()


def make_settings(**overrides: object) -> Settings:
	return Settings(_env_file=None, **overrides)


def make_service(settings: Settings):
	model = FakeModel()
	processor = FakeProcessor()
	loader = TranslationModelLoader(
		settings,
		model_factory=lambda *args, **kwargs: model,
		processor_factory=lambda *args, **kwargs: processor,
	)
	return SeamlessTranslationService(settings, loader), model, processor


def test_successful_translation_returns_structured_result() -> None:
	service, model, processor = make_service(make_settings())

	result = service.translate("Hello", "en", "hi")

	assert result.to_dict() == {
		"source_text": "Hello",
		"translated_text": "Bonjour",
		"source_language": "eng",
		"target_language": "hin",
	}
	assert processor.calls[0]["src_lang"] == "eng"
	assert model.calls[0]["tgt_lang"] == "hin"


def test_configured_languages_are_used() -> None:
	settings = make_settings(translation_source_language="eng", translation_target_language="fra")
	service, _, _ = make_service(settings)

	result = service.translate("Hello")

	assert result.source_language == "eng"
	assert result.target_language == "fra"


@pytest.mark.parametrize("source, target", [("xx", "hi"), ("en", "xx")])
def test_invalid_language_is_rejected(source: str, target: str) -> None:
	service, _, _ = make_service(make_settings())

	with pytest.raises(TranslationError, match="Unsupported language"):
		service.translate("Hello", source, target)


def test_empty_text_does_not_load_or_call_model() -> None:
	calls = 0
	settings = make_settings()
	loader = TranslationModelLoader(
		settings,
		model_factory=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError),
		processor_factory=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError),
	)
	service = SeamlessTranslationService(settings, loader)

	with pytest.raises(TranslationError, match="empty"):
		service.translate("   ", "en", "hi")

	assert calls == 0


def test_model_loading_is_lazy_and_cached() -> None:
	model_calls = 0
	processor_calls = 0
	settings = make_settings()

	def model_factory(*args, **kwargs):
		nonlocal model_calls
		model_calls += 1
		return FakeModel()

	def processor_factory(*args, **kwargs):
		nonlocal processor_calls
		processor_calls += 1
		return FakeProcessor()

	loader = TranslationModelLoader(settings, model_factory=model_factory, processor_factory=processor_factory)
	assert model_calls == 0
	assert processor_calls == 0
	loader.load()
	loader.load()
	assert model_calls == 1
	assert processor_calls == 1


def test_model_loading_and_translation_failures_are_safe() -> None:
	settings = make_settings()
	loading_service = SeamlessTranslationService(
		settings,
		TranslationModelLoader(
			settings,
			model_factory=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("private path")),
			processor_factory=lambda *args, **kwargs: FakeProcessor(),
		),
	)
	with pytest.raises(TranslationError, match="Translation failed"):
		loading_service.translate("Hello", "en", "hi")

	class FailingModel(FakeModel):
		def generate(self, **kwargs):
			raise RuntimeError("private model detail")

	failing_service = SeamlessTranslationService(
		settings,
		TranslationModelLoader(
			settings,
			model_factory=lambda *args, **kwargs: FailingModel(),
			processor_factory=lambda *args, **kwargs: FakeProcessor(),
		),
	)
	with pytest.raises(TranslationError, match="Translation failed"):
		failing_service.translate("Hello", "en", "hi")


def test_translation_can_be_disabled_without_loading_model() -> None:
	settings = make_settings(translation_enabled=False)
	loader = TranslationModelLoader(
		settings,
		model_factory=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError),
		processor_factory=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError),
	)

	assert settings.translation_enabled is False
	assert loader._loaded is None