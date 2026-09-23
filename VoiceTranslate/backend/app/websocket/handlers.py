from uuid import UUID

from fastapi import APIRouter, WebSocket
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.websockets import WebSocketDisconnect

from app.db.session import async_session_factory
from app.models.call import Call
from app.models.call_participant import CallParticipant
from app.models.user import User
from app.utils.security import InvalidTokenError, decode_token
from app.websocket.manager import connection_manager
from app.websocket.protocol import (
	InvalidMessageError,
	LanguageChangeMessage,
	PingMessage,
	error_message,
	parse_message,
	ready_message,
)

router = APIRouter(tags=["websocket"])


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
	try:
		await connection_manager.send_to_connection(websocket, ready_message(call_id, user_id))
		while True:
			received = await websocket.receive()
			if received["type"] == "websocket.disconnect":
				break
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
	except WebSocketDisconnect:
		pass
	finally:
		await connection_manager.disconnect(websocket)
