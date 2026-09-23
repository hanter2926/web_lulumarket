from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

from app.utils.constants import normalize_language_code


class PingMessage(BaseModel):
	model_config = ConfigDict(extra="forbid")
	type: Literal["ping"]


class LanguageChangeMessage(BaseModel):
	model_config = ConfigDict(extra="forbid")
	type: Literal["language.change"]
	language: str | None = Field(default=None, min_length=2, max_length=16)
	target_language: str | None = Field(default=None, min_length=2, max_length=16)

	@field_validator("language", "target_language")
	@classmethod
	def validate_language(cls, value: str | None) -> str | None:
		if value is None:
			return None
		normalize_language_code(value)
		return value.strip().lower()

	@model_validator(mode="after")
	def require_language(self) -> "LanguageChangeMessage":
		if (self.language is None) == (self.target_language is None):
			raise ValueError("Provide exactly one language field")
		return self


class AudioStartMessage(BaseModel):
	model_config = ConfigDict(extra="forbid")
	type: Literal["audio.start"]
	sample_rate: int = Field(gt=0)
	channels: int = Field(gt=0)
	sample_width: int = Field(gt=0)


class AudioEndMessage(BaseModel):
	model_config = ConfigDict(extra="forbid")
	type: Literal["audio.end"]


IncomingMessage = Annotated[
	PingMessage | LanguageChangeMessage | AudioStartMessage | AudioEndMessage,
	Field(discriminator="type"),
]
_message_adapter = TypeAdapter(IncomingMessage)


class InvalidMessageError(Exception):
	"""Raised when a client message is malformed or unsupported."""


def parse_message(raw_message: str) -> PingMessage | LanguageChangeMessage | AudioStartMessage | AudioEndMessage:
	if len(raw_message) > 4096:
		raise InvalidMessageError
	try:
		return _message_adapter.validate_json(raw_message)
	except ValueError as exc:
		raise InvalidMessageError from exc


def ready_message(call_id: str, user_id: str) -> dict[str, str]:
	return {"type": "connection.ready", "call_id": call_id, "user_id": user_id}


def error_message(code: str, message: str = "Invalid WebSocket message.") -> dict[str, str]:
	return {"type": "error", "code": code, "message": message}
