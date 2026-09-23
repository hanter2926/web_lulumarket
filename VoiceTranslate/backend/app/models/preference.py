from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class UserPreference(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "user_preferences"
    __table_args__ = (UniqueConstraint("user_id", name="uq_user_preferences_user_id"),)

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    source_language: Mapped[str] = mapped_column(String(16), nullable=False, default="en", server_default="en")
    target_language: Mapped[str] = mapped_column(String(16), nullable=False, default="hi", server_default="hi")
    voice_preference: Mapped[str | None] = mapped_column(String(120))
    speaking_speed: Mapped[float] = mapped_column(Float, nullable=False, default=1.0, server_default="1.0")
    automatic_language_detection: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    subtitles_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    translated_audio_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    user: Mapped["User"] = relationship(back_populates="preference")
