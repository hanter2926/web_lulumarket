from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from jose import JWTError, jwt
from pwdlib import PasswordHash

from app.config import get_settings

password_hash = PasswordHash.recommended()


class InvalidTokenError(Exception):
	"""Raised when a JWT cannot be trusted."""


def hash_password(password: str) -> str:
	return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
	return password_hash.verify(password, hashed_password)


def _secret_key() -> str:
	secret = get_settings().jwt_secret_key
	if not secret:
		raise RuntimeError("JWT_SECRET_KEY is not configured")
	return secret


def create_token(user_id: UUID, token_type: str, token_version: int, expires_delta: timedelta) -> str:
	now = datetime.now(UTC)
	payload = {
		"sub": str(user_id),
		"type": token_type,
		"tv": token_version,
		"jti": str(uuid4()),
		"iat": now,
		"exp": now + expires_delta,
	}
	return jwt.encode(payload, _secret_key(), algorithm=get_settings().jwt_algorithm)


def decode_token(token: str, expected_type: str) -> dict:
	try:
		payload = jwt.decode(token, _secret_key(), algorithms=[get_settings().jwt_algorithm])
	except (JWTError, RuntimeError) as exc:
		raise InvalidTokenError from exc
	if payload.get("type") != expected_type or not payload.get("sub"):
		raise InvalidTokenError
	return payload
