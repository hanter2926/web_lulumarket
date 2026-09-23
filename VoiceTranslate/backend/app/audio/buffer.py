import asyncio


class AudioBufferLimitError(ValueError):
	"""Raised when appending would exceed the configured memory limit."""


class AudioBuffer:
	def __init__(self, max_bytes: int = 1048576) -> None:
		if max_bytes <= 0:
			raise ValueError("max_bytes must be positive")
		self._max_bytes = max_bytes
		self._frames: list[bytes] = []
		self._buffered_bytes = 0
		self._lock = asyncio.Lock()

	async def append(self, frame: bytes) -> None:
		if not isinstance(frame, bytes) or not frame:
			raise ValueError("Audio buffer accepts non-empty bytes only")
		async with self._lock:
			if self._buffered_bytes + len(frame) > self._max_bytes:
				raise AudioBufferLimitError("Audio buffer limit exceeded")
			self._frames.append(frame)
			self._buffered_bytes += len(frame)

	async def read(self) -> bytes:
		async with self._lock:
			return b"".join(self._frames)

	async def clear(self) -> None:
		async with self._lock:
			self._frames.clear()
			self._buffered_bytes = 0

	async def size(self) -> int:
		async with self._lock:
			return self._buffered_bytes

	@property
	def max_bytes(self) -> int:
		return self._max_bytes
