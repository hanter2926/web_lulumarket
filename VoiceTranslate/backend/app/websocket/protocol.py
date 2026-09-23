from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter, field_validator

from app.utils.constants import SUPPORTED_LANGUAGES


class PingMessage(BaseModel):
	type: Literal["ping"]


class LanguageChangeMessage(BaseModel):
	type: Literal["language.change"]
	language: str = Field(min_length=2, max_length=16)

	@field_validator("language")
	@classmethod
	def validate_language(cls, value: str) -> str:
		normalized = value.lower()
		if normalized not in SUPPORTED_LANGUAGES:
			raise ValueError("Unsupported language")
		return normalized


IncomingMessage = Annotated[PingMessage | LanguageChangeMessage, Field(discriminator="type")]
_message_adapter = TypeAdapter(IncomingMessage)


class InvalidMessageError(Exception):
	"""Raised when a client message is malformed or unsupported."""


def parse_message(raw_message: str) -> PingMessage | LanguageChangeMessage:
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
