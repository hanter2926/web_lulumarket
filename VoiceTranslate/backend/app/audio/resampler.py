from app.audio.validator import AudioFormat, CANONICAL_PCM_FORMAT


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
		if source_format != self.target_format:
			raise UnsupportedResamplingError("Resampling this source format is not implemented")
		return payload
