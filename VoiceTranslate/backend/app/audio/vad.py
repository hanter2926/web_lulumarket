"""Lightweight, replaceable voice activity detection primitives."""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from math import sqrt
import struct
from struct import iter_unpack

from app.audio.validator import AudioValidationError, CANONICAL_PCM_FORMAT, validate_pcm_frame


class VadState(StrEnum):
	IDLE = "IDLE"
	POSSIBLE_SPEECH = "POSSIBLE_SPEECH"
	SPEAKING = "SPEAKING"
	POSSIBLE_SILENCE = "POSSIBLE_SILENCE"


@dataclass(frozen=True)
class SpeechSegment:
	start_timestamp: str
	end_timestamp: str
	duration_ms: int
	frame_count: int
	byte_count: int


@dataclass(frozen=True)
class VadEvent:
	type: str
	segment: SpeechSegment | None = None


@dataclass(frozen=True)
class VadConfig:
	enabled: bool = True
	threshold: float = 500.0
	min_speech_ms: int = 200
	min_silence_ms: int = 300
	max_speech_ms: int = 30000
	frame_ms: int = 20

	def __post_init__(self) -> None:
		if self.threshold < 0 or self.min_speech_ms <= 0 or self.min_silence_ms <= 0:
			raise ValueError("VAD thresholds and durations must be valid")
		if self.max_speech_ms < self.min_speech_ms or self.frame_ms <= 0:
			raise ValueError("VAD maximum and frame duration must be valid")


class EnergyVAD:
	"""Deterministic RMS VAD that can later be replaced behind this interface."""

	def __init__(self, config: VadConfig | None = None) -> None:
		self.config = config or VadConfig()
		self.state = VadState.IDLE
		self._speech_ms = 0
		self._silence_ms = 0
		self._frame_count = 0
		self._byte_count = 0
		self._start_timestamp: str | None = None

	@property
	def enabled(self) -> bool:
		return self.config.enabled

	def process(self, frame: bytes) -> list[VadEvent]:
		if not self.enabled:
			return []
		validate_pcm_frame(frame, CANONICAL_PCM_FORMAT)
		frame_ms = self.config.frame_ms
		is_speech = self._rms(frame) >= self.config.threshold
		if is_speech:
			return self._process_speech(frame_ms, len(frame))
		return self._process_silence(frame_ms)

	def end(self) -> list[VadEvent]:
		if self.state not in (VadState.SPEAKING, VadState.POSSIBLE_SILENCE):
			self.reset()
			return []
		event = self._end_segment()
		self.reset()
		return [event]

	def reset(self) -> None:
		self.state = VadState.IDLE
		self._speech_ms = 0
		self._silence_ms = 0
		self._frame_count = 0
		self._byte_count = 0
		self._start_timestamp = None

	def _process_speech(self, frame_ms: int, byte_count: int) -> list[VadEvent]:
		if self.state == VadState.IDLE:
			self.state = VadState.POSSIBLE_SPEECH
			self._start_timestamp = datetime.now(timezone.utc).isoformat()
		self._speech_ms += frame_ms
		self._silence_ms = 0
		self._frame_count += 1
		self._byte_count += byte_count
		if self.state == VadState.POSSIBLE_SPEECH and self._speech_ms >= self.config.min_speech_ms:
			self.state = VadState.SPEAKING
			return [VadEvent("speech.started")]
		if self.state == VadState.SPEAKING and self._speech_ms >= self.config.max_speech_ms:
			event = self._end_segment()
			self.reset()
			return [event]
		if self.state == VadState.POSSIBLE_SILENCE:
			self.state = VadState.SPEAKING
		return []

	def _process_silence(self, frame_ms: int) -> list[VadEvent]:
		if self.state == VadState.POSSIBLE_SPEECH:
			self.reset()
			return []
		if self.state not in (VadState.SPEAKING, VadState.POSSIBLE_SILENCE):
			return []
		self.state = VadState.POSSIBLE_SILENCE
		self._silence_ms += frame_ms
		if self._speech_ms >= self.config.max_speech_ms or self._silence_ms >= self.config.min_silence_ms:
			event = self._end_segment()
			self.reset()
			return [event]
		return []

	def _end_segment(self) -> VadEvent:
		return VadEvent(
			"speech.ended",
			SpeechSegment(
				start_timestamp=self._start_timestamp or datetime.now(timezone.utc).isoformat(),
				end_timestamp=datetime.now(timezone.utc).isoformat(),
				duration_ms=self._speech_ms,
				frame_count=self._frame_count,
				byte_count=self._byte_count,
			),
		)

	@staticmethod
	def _rms(frame: bytes) -> float:
		try:
			samples = tuple(sample[0] for sample in iter_unpack("<h", frame))
		except struct.error as exc:
			raise AudioValidationError("Invalid PCM audio frame") from exc
		return sqrt(sum(sample * sample for sample in samples) / len(samples))
