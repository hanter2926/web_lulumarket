from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.call import Call
    from app.models.user import User


class CallParticipant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "call_participants"
    __table_args__ = (
        UniqueConstraint("call_id", "user_id", name="uq_call_participants_call_user"),
        Index("ix_call_participants_user_id", "user_id"),
    )

    call_id: Mapped[UUID] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False, default="participant", server_default="participant")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="invited", server_default="invited")

    call: Mapped["Call"] = relationship(back_populates="participants")
    user: Mapped["User"] = relationship(back_populates="call_participations")
