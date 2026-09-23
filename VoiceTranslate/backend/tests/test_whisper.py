from dataclasses import dataclass

import pytest

from app.ai.whisper.loader import WhisperModelLoader
from app.ai.whisper.service import WhisperSTTError, WhisperSTTService
from app.config import Settings


AUDIO = b"\x00\x00" * 160


@dataclass
class FakeSegment:
    start: float
    end: float
    text: str


@dataclass
class FakeInfo:
    language: str = "en"
    language_probability: float = 0.98
    duration: float = 0.5


class FakeModel:
    def __init__(self) -> None:
        self.languages: list[str | None] = []

    def transcribe(self, audio, *, language, beam_size, vad_filter):
        self.languages.append(language)
        assert len(audio) == 160
        assert beam_size == 5
        assert vad_filter is False
        return [FakeSegment(0.0, 0.25, " hello "), FakeSegment(0.25, 0.5, "world")], FakeInfo()


def make_settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)


def test_successful_transcription_returns_structured_output() -> None:
    model = FakeModel()
    loader = WhisperModelLoader(make_settings(), model_factory=lambda *args, **kwargs: model)

    result = WhisperSTTService(make_settings(), loader).transcribe(AUDIO)

    assert result.to_dict() == {
        "text": "hello world",
        "language": "en",
        "language_probability": 0.98,
        "duration": 0.5,
        "segments": [
            {"start": 0.0, "end": 0.25, "text": "hello"},
            {"start": 0.25, "end": 0.5, "text": "world"},
        ],
    }


def test_configured_language_is_passed_to_model() -> None:
    model = FakeModel()
    settings = make_settings(whisper_language="es")
    service = WhisperSTTService(settings, WhisperModelLoader(settings, model_factory=lambda *args, **kwargs: model))

    service.transcribe(AUDIO)

    assert model.languages == ["es"]


def test_empty_language_enables_detection() -> None:
    model = FakeModel()
    settings = make_settings(whisper_language="")
    service = WhisperSTTService(settings, WhisperModelLoader(settings, model_factory=lambda *args, **kwargs: model))

    service.transcribe(AUDIO)

    assert model.languages == [None]


def test_invalid_or_empty_audio_is_rejected() -> None:
    model = FakeModel()
    service = WhisperSTTService(make_settings(), WhisperModelLoader(make_settings(), model_factory=lambda *args, **kwargs: model))

    with pytest.raises(WhisperSTTError):
        service.transcribe(b"")
    with pytest.raises(WhisperSTTError):
        service.transcribe(b"\x00")


def test_model_loading_is_lazy_and_cached() -> None:
    calls: list[tuple[tuple, dict]] = []
    model = FakeModel()

    def factory(*args, **kwargs):
        calls.append((args, kwargs))
        return model

    settings = make_settings()
    loader = WhisperModelLoader(settings, model_factory=factory)
    assert calls == []

    loader.load()
    loader.load()

    assert len(calls) == 1
    assert calls[0][0] == ("small",)
    assert calls[0][1] == {"device": "cpu", "compute_type": "int8"}


def test_model_loading_failure_is_safe() -> None:
    settings = make_settings()
    service = WhisperSTTService(
        settings,
        WhisperModelLoader(settings, model_factory=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("secret path"))),
    )

    with pytest.raises(WhisperSTTError, match="Speech transcription failed"):
        service.transcribe(AUDIO)


def test_transcription_failure_is_safe() -> None:
    class FailingModel(FakeModel):
        def transcribe(self, audio, *, language, beam_size, vad_filter):
            raise RuntimeError("internal model details")

    settings = make_settings()
    service = WhisperSTTService(
        settings,
        WhisperModelLoader(settings, model_factory=lambda *args, **kwargs: FailingModel()),
    )

    with pytest.raises(WhisperSTTError, match="Speech transcription failed"):
        service.transcribe(AUDIO)