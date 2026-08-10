from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ._base import Base

if TYPE_CHECKING:
    from ._system import System


class SystemAlias(Base):
    name: Mapped[str] = mapped_column(index=True, unique=True)
    system_id: Mapped[int] = mapped_column(ForeignKey("system.id"), index=True)

    # Relationships
    system: Mapped[System] = relationship(back_populates="aliases", lazy="noload")

    __table_args__ = (UniqueConstraint("name", "system_id"),)
