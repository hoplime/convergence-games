# pyright: reportImportCycles=false
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ._base import Base

if TYPE_CHECKING:
    from ._party import Party
    from ._user import User


class PartyUserLink(Base):
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), primary_key=True)
    party_id: Mapped[int] = mapped_column(ForeignKey("party.id", ondelete="CASCADE"), primary_key=True)
    is_leader: Mapped[bool] = mapped_column(default=False, server_default="0")

    user: Mapped[User] = relationship(back_populates="party_user_links", foreign_keys=user_id, lazy="noload")
    party: Mapped[Party] = relationship(back_populates="party_user_links", foreign_keys=party_id, lazy="noload")

    __table_args__ = (
        UniqueConstraint("user_id", "party_id"),
        Index(
            "ix_unique_party_leader",
            "party_id",
            unique=True,
            postgresql_where=(is_leader == True),  # noqa: E712 - We need to compare to True to make it a condition instead of a Mapped
        ),
    )
