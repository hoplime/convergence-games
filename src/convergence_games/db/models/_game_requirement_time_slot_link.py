from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import Connection, ForeignKey, UniqueConstraint
from sqlalchemy import event as sqla_event
from sqlalchemy.orm import Mapped, Mapper, mapped_column, relationship

from ._base import Base, foreign_key_constraint_with_event

if TYPE_CHECKING:
    from ._event import Event
    from ._game_requirement import GameRequirement
    from ._time_slot import TimeSlot


class GameRequirementTimeSlotLink(Base):
    time_slot_id: Mapped[int] = mapped_column(ForeignKey("time_slot.id"), primary_key=True)
    game_requirement_id: Mapped[int] = mapped_column(ForeignKey("game_requirement.id"), primary_key=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("event.id"), index=True
    )  # Logically redundant, but necessary for constraints

    time_slot: Mapped[TimeSlot] = relationship(
        back_populates="game_requirement_links", foreign_keys=time_slot_id, lazy="noload"
    )
    game_requirement: Mapped[GameRequirement] = relationship(
        back_populates="time_slot_links", foreign_keys=game_requirement_id, lazy="noload"
    )
    event: Mapped[Event] = relationship(back_populates="game_requirement_time_slot_links", lazy="noload")

    __table_args__ = (
        # This redundant constraint is necessary for the foreign key constraint in Session
        UniqueConstraint("id", "event_id"),
        UniqueConstraint("time_slot_id", "game_requirement_id"),
        foreign_key_constraint_with_event("game_requirement_time_slot_link", "time_slot"),
        foreign_key_constraint_with_event("game_requirement_time_slot_link", "game_requirement"),
    )


@sqla_event.listens_for(GameRequirementTimeSlotLink, "before_insert")
def game_requirement_time_slot_link_before_insert(
    mapper: Mapper[Any], connection: Connection, target: GameRequirementTimeSlotLink
):
    if target.event_id is None:
        if target.time_slot is not None:
            target.event_id = target.time_slot.event_id
        elif target.game_requirement is not None:
            target.event_id = target.game_requirement.event_id
