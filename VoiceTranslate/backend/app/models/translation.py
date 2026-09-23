from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.call import Call
    from app.models.user import User


class TranslationSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "translation_sessions"
    __table_args__ = (Index("ix_translation_sessions_call_id", "call_id"),)

    call_id: Mapped[UUID] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    source_language: Mapped[str] = mapped_column(String(16), nullable=False)
    target_language: Mapped[str] = mapped_column(String(16), nullable=False)

    call: Mapped["Call"] = relationship(back_populates="translation_sessions")
    user: Mapped["User"] = relationship(back_populates="translation_sessions")
    chunks: Mapped[list["TranslationChunk"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="TranslationChunk.sequence"
    )


class TranslationChunk(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "translation_chunks"
    __table_args__ = (Index("ix_translation_chunks_session_id", "session_id"),)

    session_id: Mapped[UUID] = mapped_column(ForeignKey("translation_sessions.id", ondelete="CASCADE"), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    transcript_text: Mapped[str] = mapped_column(Text, nullable=False)
    translation_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_language: Mapped[str] = mapped_column(String(16), nullable=False)
    target_language: Mapped[str] = mapped_column(String(16), nullable=False)

    session: Mapped["TranslationSession"] = relationship(back_populates="chunks")
