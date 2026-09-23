from array import array

from app.audio.validator import AudioValidationError, CANONICAL_PCM_FORMAT, validate_pcm_frame


def decode_pcm16le(payload: bytes) -> tuple[int, ...]:
	"""Decode canonical PCM bytes into signed samples without retaining audio."""
	validate_pcm_frame(payload, CANONICAL_PCM_FORMAT)
	samples = array("h")
	samples.frombytes(payload)
	if samples.itemsize != 2:
		raise AudioValidationError("Platform does not support 16-bit PCM decoding")
	if __import__("sys").byteorder != "little":
		samples.byteswap()
	return tuple(samples)
