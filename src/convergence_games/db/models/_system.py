# pyright: reportImportCycles=false
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from convergence_games.db.enums import SubmissionStatus

from ._base import Base

if TYPE_CHECKING:
    from ._game import Game
    from ._system_alias import SystemAlias


class System(Base):
    name: Mapped[str] = mapped_column(index=True, unique=True)
    description: Mapped[str] = mapped_column(default="")
    submission_status: Mapped[SubmissionStatus] = mapped_column(
        Enum(SubmissionStatus), default=SubmissionStatus.SUBMITTED, index=True
    )

    # Relationships
    games: Mapped[list[Game]] = relationship(back_populates="system", lazy="noload")
    aliases: Mapped[list[SystemAlias]] = relationship(back_populates="system", lazy="noload")
