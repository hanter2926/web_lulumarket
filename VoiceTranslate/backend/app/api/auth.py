from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.dependencies import get_current_active_user
from app.db.session import get_session
from app.models.user import User
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse, UserResponse
from app.services.auth_service import (
	AuthenticationError,
	DuplicateEmailError,
	authenticate_user,
	get_user_by_id,
	invalidate_tokens,
	issue_tokens,
	register_user,
)
from app.utils.security import InvalidTokenError, decode_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest, session: AsyncSession = Depends(get_session)) -> User:
	try:
		return await register_user(session, request)
	except DuplicateEmailError:
		raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered") from None


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, session: AsyncSession = Depends(get_session)) -> TokenResponse:
	try:
		user = await authenticate_user(session, request.email, request.password)
	except AuthenticationError:
		raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password") from None
	return issue_tokens(user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: RefreshRequest, session: AsyncSession = Depends(get_session)) -> TokenResponse:
	try:
		payload = decode_token(request.refresh_token, "refresh")
		user_id = UUID(payload["sub"])
		token_version = int(payload["tv"])
	except (InvalidTokenError, KeyError, TypeError, ValueError):
		raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token") from None

	user = await get_user_by_id(session, user_id)
	if user is None or not user.is_active or user.token_version != token_version:
		raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")
	return issue_tokens(user)


@router.post("/logout")
async def logout(
	user: User = Depends(get_current_active_user), session: AsyncSession = Depends(get_session)
) -> dict[str, str]:
	await invalidate_tokens(session, user)
	return {"message": "Logged out successfully"}
