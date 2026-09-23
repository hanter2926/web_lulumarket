from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
	email: EmailStr
	password: str = Field(min_length=8, max_length=128)
	display_name: str = Field(min_length=1, max_length=120)

	@field_validator("password")
	@classmethod
	def validate_password(cls, value: str) -> str:
		if not any(character.islower() for character in value):
			raise ValueError("Password must contain a lowercase letter")
		if not any(character.isupper() for character in value):
			raise ValueError("Password must contain an uppercase letter")
		if not any(character.isdigit() for character in value):
			raise ValueError("Password must contain a number")
		return value


class LoginRequest(BaseModel):
	email: EmailStr
	password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
	refresh_token: str = Field(min_length=1)


class TokenResponse(BaseModel):
	access_token: str
	refresh_token: str
	token_type: str = "bearer"
	expires_in: int


class UserResponse(BaseModel):
	model_config = ConfigDict(from_attributes=True)

	id: UUID
	email: EmailStr
	display_name: str
	is_active: bool
	is_email_verified: bool
