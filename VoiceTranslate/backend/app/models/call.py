from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.call_participant import CallParticipant
    from app.models.translation import TranslationSession
    from app.models.user import User


class Call(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "calls"
    __table_args__ = (Index("ix_calls_initiator_id", "initiator_id"), Index("ix_calls_status", "status"))

    initiator_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="created", server_default="created")

    initiator: Mapped["User"] = relationship(back_populates="initiated_calls")
    participants: Mapped[list["CallParticipant"]] = relationship(
        back_populates="call", cascade="all, delete-orphan"
    )
    translation_sessions: Mapped[list["TranslationSession"]] = relationship(
        back_populates="call", cascade="all, delete-orphan"
    )
