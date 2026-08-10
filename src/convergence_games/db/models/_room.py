from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from convergence_games.db.enums import RoomFacility

from ._base import Base

if TYPE_CHECKING:
    from ._event import Event
    from ._table import Table


class Room(Base):
    name: Mapped[str] = mapped_column(default="")
    description: Mapped[str] = mapped_column(default="")
    facilities: Mapped[RoomFacility] = mapped_column(Integer, default=RoomFacility.NONE, server_default="0")

    # Foreign Keys
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id"), index=True)

    # Relationships
    event: Mapped[Event] = relationship(back_populates="rooms", lazy="noload")
    tables: Mapped[list[Table]] = relationship(
        back_populates="room", foreign_keys="Table.room_id", lazy="noload", order_by="Table.name"
    )

    __table_args__ = (
        # This redundant constraint is necessary for the foreign key constraint in Session
        UniqueConstraint("id", "event_id"),
    )
