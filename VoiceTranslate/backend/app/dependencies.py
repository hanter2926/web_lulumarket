from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.user import User
from app.services.auth_service import get_user_by_id
from app.utils.security import InvalidTokenError, decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
	token: str = Depends(oauth2_scheme), session: AsyncSession = Depends(get_session)
) -> User:
	credentials_exception = HTTPException(
		status_code=status.HTTP_401_UNAUTHORIZED,
		detail="Invalid or expired authentication token",
		headers={"WWW-Authenticate": "Bearer"},
	)
	try:
		payload = decode_token(token, "access")
		user_id = UUID(payload["sub"])
		token_version = int(payload["tv"])
	except (InvalidTokenError, KeyError, TypeError, ValueError):
		raise credentials_exception from None

	user = await get_user_by_id(session, user_id)
	if user is None or not user.is_active or user.token_version != token_version:
		raise credentials_exception
	return user


async def get_current_active_user(user: User = Depends(get_current_user)) -> User:
	if not user.is_active:
		raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")
	return user
