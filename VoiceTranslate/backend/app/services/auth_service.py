from datetime import timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.user import User
from app.schemas.auth import RegisterRequest, TokenResponse
from app.utils.security import create_token, hash_password, verify_password


class AuthenticationError(Exception):
	"""Raised when credentials or account state are invalid."""


class DuplicateEmailError(Exception):
	"""Raised when an email is already registered."""


async def register_user(session: AsyncSession, request: RegisterRequest) -> User:
	email = request.email.lower()
	existing_user = await session.scalar(select(User).where(User.email == email))
	if existing_user is not None:
		raise DuplicateEmailError

	user = User(email=email, password_hash=hash_password(request.password), display_name=request.display_name)
	session.add(user)
	try:
		await session.commit()
	except IntegrityError as exc:
		await session.rollback()
		raise DuplicateEmailError from exc
	await session.refresh(user)
	return user


async def authenticate_user(session: AsyncSession, email: str, password: str) -> User:
	user = await session.scalar(select(User).where(User.email == email.lower()))
	if user is None or not user.is_active or not verify_password(password, user.password_hash):
		raise AuthenticationError
	return user


def issue_tokens(user: User) -> TokenResponse:
	settings = get_settings()
	access_token = create_token(
		user.id, "access", user.token_version, timedelta(minutes=settings.access_token_expire_minutes)
	)
	refresh_token = create_token(
		user.id, "refresh", user.token_version, timedelta(days=settings.refresh_token_expire_days)
	)
	return TokenResponse(
		access_token=access_token,
		refresh_token=refresh_token,
		expires_in=settings.access_token_expire_minutes * 60,
	)


async def get_user_by_id(session: AsyncSession, user_id: UUID) -> User | None:
	return await session.get(User, user_id)


async def invalidate_tokens(session: AsyncSession, user: User) -> None:
	user.token_version += 1
	await session.commit()
