from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ._base import Base

if TYPE_CHECKING:
    from ._content_warning import ContentWarning
    from ._game import Game


class GameContentWarningLink(Base):
    game_id: Mapped[int] = mapped_column(ForeignKey("game.id"), primary_key=True)
    content_warning_id: Mapped[int] = mapped_column(ForeignKey("content_warning.id"), primary_key=True)

    game: Mapped[Game] = relationship(back_populates="content_warning_links", lazy="noload")
    content_warning: Mapped[ContentWarning] = relationship(back_populates="game_links", lazy="noload")

    __table_args__ = (UniqueConstraint("game_id", "content_warning_id"),)
