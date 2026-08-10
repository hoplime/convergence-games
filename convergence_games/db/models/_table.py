from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import Connection, Enum, ForeignKey, Integer, UniqueConstraint
from sqlalchemy import event as sqla_event
from sqlalchemy.orm import Mapped, Mapper, mapped_column, relationship

from convergence_games.db.enums import TableFacility, TableSize

from ._base import Base, foreign_key_constraint_with_event

if TYPE_CHECKING:
    from ._event import Event
    from ._room import Room
    from ._session import Session


class Table(Base):
    name: Mapped[str] = mapped_column(default="")
    facilities: Mapped[TableFacility] = mapped_column(Integer, default=TableFacility.NONE, server_default="0")
    size: Mapped[TableSize] = mapped_column(
        Enum(TableSize), default=TableSize.SMALL, server_default="SMALL", index=True
    )

    # Foreign Keys
    room_id: Mapped[int] = mapped_column(ForeignKey("room.id"), index=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("event.id"), index=True
    )  # Logically redundant, but necessary for constraints

    # Relationships
    room: Mapped[Room] = relationship(back_populates="tables", foreign_keys=room_id, lazy="noload")
    event: Mapped[Event] = relationship(back_populates="tables", lazy="noload")
    sessions: Mapped[list[Session]] = relationship(
        back_populates="table", foreign_keys="Session.table_id", lazy="noload"
    )

    __table_args__ = (
        # This redundant constraint is necessary for the foreign key constraint in Session
        UniqueConstraint("id", "event_id"),
        foreign_key_constraint_with_event("table", "room"),
    )


@sqla_event.listens_for(Table, "before_insert")
def table_before_insert(mapper: Mapper[Any], connection: Connection, target: Table):
    if target.event_id is None:
        target.event_id = target.room.event_id
