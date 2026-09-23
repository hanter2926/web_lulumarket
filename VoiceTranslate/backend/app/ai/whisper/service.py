"""Speech-to-text service interface."""

from dataclasses import dataclass
from typing import Any

import numpy as np

from app.audio.validator import AudioValidationError, CANONICAL_PCM_FORMAT, validate_pcm_frame
from app.config import Settings
from app.ai.whisper.loader import WhisperModelLoader, get_shared_whisper_model_loader


class WhisperSTTError(RuntimeError):
	"""Raised when a speech segment cannot be transcribed safely."""


@dataclass(frozen=True)
class Transcript:
	text: str
	language: str
	language_probability: float
	duration: float
	segments: list[dict[str, Any]]

	def to_dict(self) -> dict[str, Any]:
		return {
			"text": self.text,
			"language": self.language,
			"language_probability": self.language_probability,
			"duration": self.duration,
			"segments": self.segments,
		}


class WhisperSTTService:
	def __init__(self, settings: Settings, loader: WhisperModelLoader | None = None) -> None:
		self.settings = settings
		self.loader = loader or get_shared_whisper_model_loader(settings)

	def transcribe(self, audio: bytes) -> Transcript:
		try:
			validate_pcm_frame(audio, CANONICAL_PCM_FORMAT, self.settings.max_audio_buffer_bytes)
			waveform = np.frombuffer(audio, dtype="<i2").astype(np.float32) / 32768.0
			model = self.loader.load()
			segments, info = model.transcribe(
				waveform,
				language=self.settings.whisper_language.strip() or None,
				beam_size=self.settings.whisper_beam_size,
				vad_filter=self.settings.whisper_vad_filter,
			)
			structured_segments = [
				{
					"start": float(segment.start),
					"end": float(segment.end),
					"text": str(segment.text).strip(),
				}
				for segment in segments
			]
			duration = float(getattr(info, "duration", 0.0) or 0.0)
			if not duration and structured_segments:
				duration = max(segment["end"] for segment in structured_segments)
			return Transcript(
				text=" ".join(segment["text"] for segment in structured_segments).strip(),
				language=str(getattr(info, "language", "")),
				language_probability=float(getattr(info, "language_probability", 0.0) or 0.0),
				duration=duration,
				segments=structured_segments,
			)
		except (AudioValidationError, ValueError) as exc:
			raise WhisperSTTError("Invalid speech audio") from exc
		except Exception as exc:
			raise WhisperSTTError("Speech transcription failed") from exc
