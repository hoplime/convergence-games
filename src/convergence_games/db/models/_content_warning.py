# pyright: reportImportCycles=false
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from convergence_games.db.enums import SubmissionStatus

from ._base import Base
from ._game_content_warning_link import GameContentWarningLink

if TYPE_CHECKING:
    from ._game import Game


class ContentWarning(Base):
    name: Mapped[str] = mapped_column(index=True, unique=True)
    description: Mapped[str] = mapped_column(default="")
    suggested: Mapped[bool] = mapped_column(default=False)
    submission_status: Mapped[SubmissionStatus] = mapped_column(
        Enum(SubmissionStatus), default=SubmissionStatus.SUBMITTED, index=True
    )

    # Relationships
    games: Mapped[list[Game]] = relationship(
        back_populates="content_warnings",
        secondary=GameContentWarningLink.__table__,
        viewonly=True,
        lazy="noload",
    )

    # Association Proxy Relationships
    game_links: Mapped[list[GameContentWarningLink]] = relationship(back_populates="content_warning", lazy="noload")
