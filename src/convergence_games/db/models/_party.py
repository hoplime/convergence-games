# pyright: reportImportCycles=false
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ._base import Base

if TYPE_CHECKING:
    from ._party_user_link import PartyUserLink
    from ._time_slot import TimeSlot
    from ._user import User


class Party(Base):
    # Foreign Keys
    time_slot_id: Mapped[int] = mapped_column(ForeignKey("time_slot.id"), index=True)

    # Relationships
    time_slot: Mapped[TimeSlot] = relationship(back_populates="parties", foreign_keys=time_slot_id, lazy="noload")
    members: Mapped[list[User]] = relationship(
        back_populates="parties",
        secondary="party_user_link",
        primaryjoin="Party.id == PartyUserLink.party_id",
        secondaryjoin="User.id == PartyUserLink.user_id",
        viewonly=True,
        lazy="noload",
    )

    # Association Proxy Relationships
    party_user_links: Mapped[list[PartyUserLink]] = relationship(
        back_populates="party",
        lazy="noload",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
