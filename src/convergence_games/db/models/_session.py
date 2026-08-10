from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ._base import Base, foreign_key_constraint_with_event

if TYPE_CHECKING:
    from ._allocation import Allocation
    from ._event import Event
    from ._game import Game
    from ._table import Table
    from ._time_slot import TimeSlot


class Session(Base):
    committed: Mapped[bool] = mapped_column(default=False, server_default="0", index=True)

    # Foreign Keys
    game_id: Mapped[int] = mapped_column(ForeignKey("game.id"), index=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("table.id"), index=True)
    time_slot_id: Mapped[int] = mapped_column(ForeignKey("time_slot.id"), index=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("event.id"), index=True
    )  # Logically redundant, but necessary for constraints

    # Relationships
    game: Mapped[Game] = relationship(back_populates="sessions", foreign_keys=game_id, lazy="noload")
    table: Mapped[Table] = relationship(back_populates="sessions", foreign_keys=table_id, lazy="noload")
    time_slot: Mapped[TimeSlot] = relationship(back_populates="sessions", foreign_keys=time_slot_id, lazy="noload")
    event: Mapped[Event] = relationship(back_populates="sessions", lazy="noload")
    allocations: Mapped[list[Allocation]] = relationship(
        back_populates="session",
        lazy="noload",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        # https://dba.stackexchange.com/a/58972
        # https://stackoverflow.com/a/63922398
        # These constraints ensure that the Game, Table and TimeSlot are part of the same Event
        foreign_key_constraint_with_event("session", "game"),
        foreign_key_constraint_with_event("session", "table"),
        foreign_key_constraint_with_event("session", "time_slot"),
    )
