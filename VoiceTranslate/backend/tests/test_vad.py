import pytest

from app.audio.vad import EnergyVAD, VadConfig, VadState
from app.audio.validator import AudioValidationError


SILENCE = b"\x00\x00" * 320
SPEECH = b"\xff\x7f" * 320
NOISE = b"\x64\x00" * 320


def make_vad(**overrides: object) -> EnergyVAD:
    values = {"min_speech_ms": 40, "min_silence_ms": 40, "max_speech_ms": 100}
    values.update(overrides)
    return EnergyVAD(VadConfig(**values))


def test_silence_detection() -> None:
    vad = make_vad()
    assert vad.process(SILENCE) == []
    assert vad.state == VadState.IDLE


def test_speech_start_and_continuation() -> None:
    vad = make_vad()
    assert vad.process(SPEECH) == []
    events = vad.process(SPEECH)
    assert [event.type for event in events] == ["speech.started"]
    assert vad.state == VadState.SPEAKING
    assert vad.process(SPEECH) == []


def test_speech_end_after_minimum_silence() -> None:
    vad = make_vad()
    vad.process(SPEECH)
    vad.process(SPEECH)
    assert vad.process(SILENCE) == []
    events = vad.process(SILENCE)
    assert events[0].type == "speech.ended"
    assert events[0].segment is not None
    assert events[0].segment.duration_ms == 40
    assert vad.state == VadState.IDLE


@pytest.mark.parametrize(("frame_ms", "expected_duration_ms"), ((10, 20), (40, 80)))
def test_configured_frame_duration_is_used(frame_ms: int, expected_duration_ms: int) -> None:
    vad = make_vad(frame_ms=frame_ms, min_speech_ms=1, min_silence_ms=1000)
    vad.process(SPEECH)
    vad.process(SPEECH)
    events = vad.end()

    assert events[0].segment is not None
    assert events[0].segment.duration_ms == expected_duration_ms


def test_minimum_speech_avoids_noisy_false_start() -> None:
    vad = make_vad()
    assert vad.process(NOISE) == []
    assert vad.state == VadState.IDLE


def test_maximum_speech_duration_ends_segment() -> None:
    vad = make_vad(max_speech_ms=40)
    vad.process(SPEECH)
    events = vad.process(SPEECH)
    assert events[0].type == "speech.started"
    events = vad.process(SPEECH)
    assert events[0].type == "speech.ended"
    assert vad.state == VadState.IDLE


def test_reset_discards_partial_segment() -> None:
    vad = make_vad()
    vad.process(SPEECH)
    vad.reset()
    assert vad.state == VadState.IDLE
    assert vad.process(SILENCE) == []


def test_end_flushes_active_segment_and_empty_audio_is_rejected() -> None:
    vad = make_vad()
    vad.process(SPEECH)
    vad.process(SPEECH)
    assert vad.end()[0].type == "speech.ended"
    with pytest.raises(AudioValidationError):
        vad.process(b"")
