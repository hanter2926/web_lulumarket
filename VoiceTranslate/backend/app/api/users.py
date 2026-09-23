from fastapi import APIRouter, Depends

from app.dependencies import get_current_active_user
from app.models.user import User
from app.schemas.auth import UserResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def current_user(user: User = Depends(get_current_active_user)) -> User:
	return user
