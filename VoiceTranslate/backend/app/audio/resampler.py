from app.audio.validator import AudioFormat, CANONICAL_PCM_FORMAT, validate_pcm_frame


class UnsupportedResamplingError(ValueError):
	"""Raised when a source format needs a resampling implementation."""


class PcmResampler:
	"""Boundary for future sample-rate conversion.

	Only canonical input is accepted until a dedicated resampling dependency is
	selected and tested. No audio is silently returned in the wrong format.
	"""

	def __init__(self, target_format: AudioFormat = CANONICAL_PCM_FORMAT) -> None:
		self.target_format = target_format

	def resample(self, payload: bytes, source_format: AudioFormat) -> bytes:
		if self.target_format != CANONICAL_PCM_FORMAT:
			raise UnsupportedResamplingError("Only 16 kHz mono 16-bit PCM is supported")
		if source_format != self.target_format:
			raise UnsupportedResamplingError("Resampling this source format is not implemented")
		return validate_pcm_frame(payload, source_format)
