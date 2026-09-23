from uuid import UUID
from dataclasses import dataclass

from fastapi import APIRouter, WebSocket
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.websockets import WebSocketDisconnect

from app.audio.buffer import AudioBuffer, AudioBufferLimitError
from app.audio.validator import AudioFormat, AudioValidationError, CANONICAL_PCM_FORMAT, validate_pcm_frame
from app.config import get_settings
from app.db.session import async_session_factory
from app.models.call import Call
from app.models.call_participant import CallParticipant
from app.models.user import User
from app.utils.security import InvalidTokenError, decode_token
from app.websocket.manager import connection_manager
from app.websocket.protocol import (
	InvalidMessageError,
	AudioEndMessage,
	AudioStartMessage,
	LanguageChangeMessage,
	PingMessage,
	error_message,
	parse_message,
	ready_message,
)

router = APIRouter(tags=["websocket"])


@dataclass
class AudioConnectionState:
	status: str = "IDLE"
	format: AudioFormat | None = None
	buffer: AudioBuffer | None = None


def _audio_error(code: str, message: str) -> dict[str, str]:
	return error_message(code, message)


async def _handle_audio_start(message: AudioStartMessage, state: AudioConnectionState) -> dict[str, str]:
	if state.status != "IDLE":
		return _audio_error("INVALID_AUDIO_STATE", "Audio is already started.")
	format = AudioFormat(message.sample_rate, message.channels, message.sample_width)
	if format != CANONICAL_PCM_FORMAT:
		return _audio_error("UNSUPPORTED_AUDIO_FORMAT", "Only 16 kHz mono 16-bit PCM is supported.")
	settings = get_settings()
	state.format = format
	state.buffer = AudioBuffer(settings.max_audio_buffer_bytes)
	state.status = "AUDIO_STARTED"
	return {"type": "audio.ready", "sample_rate": "16000", "channels": "1", "sample_width": "2"}


async def _handle_audio_chunk(payload: bytes, state: AudioConnectionState) -> dict[str, str]:
	if state.status == "IDLE" or state.buffer is None or state.format is None:
		return _audio_error("AUDIO_NOT_STARTED", "Send audio.start before binary audio frames.")
	settings = get_settings()
	if len(payload) > settings.max_websocket_frame_bytes or len(payload) > settings.max_audio_chunk_bytes:
		return _audio_error("FRAME_TOO_LARGE", "Audio frame exceeds the maximum size.")
	max_segment_bytes = int(state.format.sample_rate * state.format.sample_width * settings.max_audio_segment_seconds)
	if await state.buffer.size() + len(payload) > max_segment_bytes:
		return _audio_error("AUDIO_SEGMENT_TOO_LARGE", "Audio segment exceeds the maximum duration.")
	try:
		validate_pcm_frame(payload, state.format, settings.max_websocket_frame_bytes)
		await state.buffer.append(payload)
	except AudioValidationError:
		return _audio_error("INVALID_AUDIO", "Invalid PCM audio frame.")
	except AudioBufferLimitError:
		return _audio_error("AUDIO_BUFFER_LIMIT", "Audio buffer limit exceeded.")
	state.status = "RECEIVING"
	return {"type": "audio.received", "bytes": str(len(payload))}


async def _handle_audio_end(state: AudioConnectionState) -> dict[str, str]:
	if state.status == "IDLE" or state.buffer is None:
		return _audio_error("AUDIO_NOT_STARTED", "Send audio.start before audio.end.")
	total_bytes = await state.buffer.size()
	await state.buffer.clear()
	state.status = "IDLE"
	state.format = None
	state.buffer = None
	return {"type": "audio.ended", "bytes": str(total_bytes)}


async def _authenticate_and_authorize(websocket: WebSocket, session: AsyncSession, call_id: UUID) -> User | None:
	token = websocket.query_params.get("token")
	if not token:
		return None
	try:
		payload = decode_token(token, "access")
		user_id = UUID(payload["sub"])
		token_version = int(payload["tv"])
	except (InvalidTokenError, KeyError, TypeError, ValueError):
		return None

	user = await session.get(User, user_id)
	if user is None or not user.is_active or user.token_version != token_version:
		return None

	call = await session.scalar(select(Call).where(Call.id == call_id))
	if call is None:
		return None
	if call.initiator_id == user_id:
		return user
	participant = await session.scalar(
		select(CallParticipant.id).where(
			CallParticipant.call_id == call_id,
			CallParticipant.user_id == user_id,
		)
	)
	return user if participant is not None else None


@router.websocket("/ws/calls/{call_id}")
async def call_websocket(websocket: WebSocket, call_id: str) -> None:
	try:
		parsed_call_id = UUID(call_id)
	except ValueError:
		await websocket.close(code=1008, reason="Invalid call id")
		return

	async with async_session_factory() as session:
		user = await _authenticate_and_authorize(websocket, session, parsed_call_id)
		if user is None:
			await websocket.close(code=1008, reason="Authentication or authorization failed")
			return

	user_id = str(user.id)
	await connection_manager.connect(websocket, call_id, user_id)
	audio_state = AudioConnectionState()
	try:
		await connection_manager.send_to_connection(websocket, ready_message(call_id, user_id))
		while True:
			received = await websocket.receive()
			if received["type"] == "websocket.disconnect":
				break
			binary_message = received.get("bytes")
			if binary_message is not None:
				await connection_manager.send_to_connection(websocket, await _handle_audio_chunk(binary_message, audio_state))
				continue
			raw_message = received.get("text")
			if raw_message is None:
				await connection_manager.send_to_connection(websocket, error_message("INVALID_MESSAGE"))
				continue
			try:
				message = parse_message(raw_message)
			except InvalidMessageError:
				await connection_manager.send_to_connection(websocket, error_message("INVALID_MESSAGE"))
				continue

			if isinstance(message, PingMessage):
				await connection_manager.send_to_connection(websocket, {"type": "pong"})
			elif isinstance(message, LanguageChangeMessage):
				await connection_manager.send_to_connection(
					websocket,
					{"type": "language.changed", "language": message.language},
				)
			elif isinstance(message, AudioStartMessage):
				await connection_manager.send_to_connection(websocket, await _handle_audio_start(message, audio_state))
			elif isinstance(message, AudioEndMessage):
				await connection_manager.send_to_connection(websocket, await _handle_audio_end(audio_state))
	except WebSocketDisconnect:
		pass
	finally:
		await connection_manager.disconnect(websocket)
