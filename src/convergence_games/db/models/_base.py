# pyright: reportImportCycles=false
from __future__ import annotations

from typing import TYPE_CHECKING

from advanced_alchemy.base import BigIntAuditBase
from sqlalchemy import ForeignKey, ForeignKeyConstraint
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, relationship

from convergence_games.lib.context import user_id_ctx

if TYPE_CHECKING:
    from ._user import User


class UserAuditColumns:
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("user.id"),
        nullable=True,
        default=user_id_ctx.get,
    )
    updated_by: Mapped[int | None] = mapped_column(
        ForeignKey("user.id"),
        nullable=True,
        default=user_id_ctx.get,
        onupdate=user_id_ctx.get,
    )

    @declared_attr
    def created_by_user(self) -> Mapped[User | None]:
        return relationship(
            "User",
            foreign_keys=[self.created_by],  # pyright: ignore[reportArgumentType]
            lazy="noload",
            viewonly=True,
        )

    @declared_attr
    def updated_by_user(self) -> Mapped[User | None]:
        return relationship(
            "User",
            foreign_keys=[self.updated_by],  # pyright: ignore[reportArgumentType]
            lazy="noload",
            viewonly=True,
        )


class Base(BigIntAuditBase, UserAuditColumns):
    __abstract__ = True


def foreign_key_constraint_with_event(
    this_table_name: str, foreign_table_name: str, foreign_table_id_name: str | None = None
) -> ForeignKeyConstraint:
    if foreign_table_id_name is None:
        foreign_table_id_name = foreign_table_name + "_id"
    desired_name = f"fk_{this_table_name}_{foreign_table_name}_with_event"
    return ForeignKeyConstraint(
        [foreign_table_id_name, "event_id"],
        [foreign_table_name + ".id", foreign_table_name + ".event_id"],
        name=desired_name[:63],
    )
