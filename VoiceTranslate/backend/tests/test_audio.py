import asyncio

import pytest

from app.audio.buffer import AudioBuffer, AudioBufferLimitError
from app.audio.decoder import decode_pcm16le
from app.audio.resampler import PcmResampler, UnsupportedResamplingError
from app.audio.validator import AudioFormat, AudioValidationError, CANONICAL_PCM_FORMAT, validate_pcm_frame


def test_valid_pcm_frame() -> None:
    payload = b"\x00\x00\x01\x00"
    assert validate_pcm_frame(payload) == payload
    assert decode_pcm16le(payload) == (0, 1)


def test_empty_frame_rejected() -> None:
    with pytest.raises(AudioValidationError):
        validate_pcm_frame(b"")


def test_oversized_frame_rejected() -> None:
    with pytest.raises(AudioValidationError):
        validate_pcm_frame(b"\x00\x00", max_frame_bytes=1)


def test_invalid_pcm_payload_rejected() -> None:
    with pytest.raises(AudioValidationError):
        validate_pcm_frame(b"\x00")
    with pytest.raises(AudioValidationError):
        validate_pcm_frame("not bytes")  # type: ignore[arg-type]


def test_unsupported_audio_format_rejected() -> None:
    with pytest.raises(AudioValidationError):
        validate_pcm_frame(b"\x00\x00", AudioFormat(8000, 1, 2))


def test_buffer_append_read_and_clear() -> None:
    async def scenario() -> None:
        buffer = AudioBuffer(max_bytes=8)
        await buffer.append(b"12")
        await buffer.append(b"34")
        assert await buffer.read() == b"1234"
        assert await buffer.size() == 4
        await buffer.clear()
        assert await buffer.read() == b""
        assert await buffer.size() == 0

    asyncio.run(scenario())


def test_buffer_size_limit_rejects_without_growth() -> None:
    async def scenario() -> None:
        buffer = AudioBuffer(max_bytes=4)
        await buffer.append(b"1234")
        with pytest.raises(AudioBufferLimitError):
            await buffer.append(b"5")
        assert await buffer.read() == b"1234"

    asyncio.run(scenario())


def test_resampler_accepts_only_canonical_input() -> None:
    resampler = PcmResampler()
    payload = b"\x00\x00"
    assert resampler.resample(payload, CANONICAL_PCM_FORMAT) == payload
    with pytest.raises(UnsupportedResamplingError):
        resampler.resample(payload, AudioFormat(8000, 1, 2))
