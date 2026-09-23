import asyncio
from collections import defaultdict
from dataclasses import dataclass

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect


@dataclass(frozen=True)
class Connection:
	websocket: WebSocket
	call_id: str
	user_id: str


class ConnectionManager:
	def __init__(self) -> None:
		self._connections: dict[WebSocket, Connection] = {}
		self._by_call: defaultdict[str, set[WebSocket]] = defaultdict(set)
		self._by_user: defaultdict[str, set[WebSocket]] = defaultdict(set)
		self._lock = asyncio.Lock()

	async def connect(self, websocket: WebSocket, call_id: str, user_id: str) -> None:
		await websocket.accept()
		connection = Connection(websocket=websocket, call_id=call_id, user_id=user_id)
		async with self._lock:
			self._connections[websocket] = connection
			self._by_call[call_id].add(websocket)
			self._by_user[user_id].add(websocket)

	async def disconnect(self, websocket: WebSocket) -> None:
		async with self._lock:
			connection = self._connections.pop(websocket, None)
			if connection is None:
				return
			call_connections = self._by_call[connection.call_id]
			user_connections = self._by_user[connection.user_id]
			call_connections.discard(websocket)
			user_connections.discard(websocket)
			if not call_connections:
				del self._by_call[connection.call_id]
			if not user_connections:
				del self._by_user[connection.user_id]

	async def send_to_connection(self, websocket: WebSocket, message: dict) -> bool:
		try:
			await websocket.send_json(message)
			return True
		except (WebSocketDisconnect, RuntimeError, OSError):
			await self.disconnect(websocket)
			return False

	async def send_to_user(self, user_id: str, message: dict) -> None:
		async with self._lock:
			connections = tuple(self._by_user.get(user_id, ()))
		await asyncio.gather(*(self.send_to_connection(connection, message) for connection in connections))

	async def send_to_call(self, call_id: str, message: dict) -> None:
		async with self._lock:
			connections = tuple(self._by_call.get(call_id, ()))
		await asyncio.gather(*(self.send_to_connection(connection, message) for connection in connections))

	async def broadcast_to_call(self, call_id: str, message: dict) -> None:
		await self.send_to_call(call_id, message)

	async def connection_count(self, call_id: str | None = None) -> int:
		async with self._lock:
			if call_id is None:
				return len(self._connections)
			return len(self._by_call.get(call_id, ()))


connection_manager = ConnectionManager()
