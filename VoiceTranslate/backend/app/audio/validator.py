from dataclasses import dataclass


class AudioValidationError(ValueError):
	"""Raised when a binary payload is not a supported PCM frame."""


@dataclass(frozen=True)
class AudioFormat:
	sample_rate: int
	channels: int
	sample_width: int
	little_endian: bool = True


CANONICAL_PCM_FORMAT = AudioFormat(sample_rate=16000, channels=1, sample_width=2)


def validate_pcm_frame(
	payload: bytes,
	audio_format: AudioFormat = CANONICAL_PCM_FORMAT,
	max_frame_bytes: int = 65536,
) -> bytes:
	if not isinstance(payload, bytes):
		raise AudioValidationError("Audio frame must be binary PCM data")
	if not payload:
		raise AudioValidationError("Audio frame must not be empty")
	if len(payload) > max_frame_bytes:
		raise AudioValidationError("Audio frame exceeds the maximum size")
	if audio_format != CANONICAL_PCM_FORMAT:
		raise AudioValidationError("Only 16 kHz mono 16-bit little-endian PCM is supported")
	if audio_format.channels != 1 or audio_format.sample_width != 2 or not audio_format.little_endian:
		raise AudioValidationError("Only mono 16-bit little-endian PCM is supported")
	if len(payload) % audio_format.sample_width != 0:
		raise AudioValidationError("PCM frame contains an incomplete sample")
	return payload
