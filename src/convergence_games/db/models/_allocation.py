# pyright: reportImportCycles=false
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ._base import Base

if TYPE_CHECKING:
    from ._session import Session
    from ._user import User


class Allocation(Base):
    committed: Mapped[bool] = mapped_column(default=False, server_default="0", index=True)

    # Foreign Keys
    party_leader_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("session.id", ondelete="CASCADE"), index=True)

    # Relationships
    party_leader: Mapped[User] = relationship(back_populates="allocations", foreign_keys=party_leader_id, lazy="noload")
    session: Mapped[Session] = relationship(back_populates="allocations", foreign_keys=session_id, lazy="noload")

    __table_args__ = (UniqueConstraint("party_leader_id", "session_id", "committed"),)
