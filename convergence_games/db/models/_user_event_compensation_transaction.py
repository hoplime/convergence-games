from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ._base import Base

if TYPE_CHECKING:
    from ._event import Event
    from ._time_slot import TimeSlot
    from ._user import User


class UserEventCompensationTransaction(Base):
    current_balance: Mapped[int] = mapped_column(default=0)
    previous_balance: Mapped[int] = mapped_column(default=0)
    delta: Mapped[int] = mapped_column(default=0)

    # Foreign Keys
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)
    previous_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_event_compensation_transaction.id"), index=True, nullable=True
    )
    associated_time_slot_id: Mapped[int | None] = mapped_column(ForeignKey("time_slot.id"), index=True, nullable=True)

    # Relationships
    event: Mapped[Event] = relationship(back_populates="compensation_transactions", lazy="noload")
    user: Mapped[User] = relationship(
        back_populates="compensation_transactions",
        primaryjoin="User.id == UserEventCompensationTransaction.user_id",
        lazy="noload",
    )
    previous_transaction: Mapped[UserEventCompensationTransaction | None] = relationship(
        foreign_keys=[event_id, user_id, previous_transaction_id],
        remote_side="UserEventCompensationTransaction.event_id, UserEventCompensationTransaction.user_id, UserEventCompensationTransaction.id",
        back_populates="next_transaction",
        lazy="noload",
        viewonly=True,
    )
    next_transaction: Mapped[UserEventCompensationTransaction | None] = relationship(
        foreign_keys="UserEventCompensationTransaction.event_id, UserEventCompensationTransaction.user_id, UserEventCompensationTransaction.id",
        remote_side=[event_id, user_id, previous_transaction_id],
        back_populates="previous_transaction",
        lazy="noload",
        viewonly=True,
    )
    associated_time_slot: Mapped[TimeSlot | None] = relationship(
        back_populates="compensation_transactions", lazy="noload", viewonly=True
    )

    __table_args__ = (
        UniqueConstraint("previous_transaction_id"),
        # We need to make sure that all transactions in a chain point to the same event and user
        UniqueConstraint("event_id", "user_id", "id", name="uq_compensation_transaction_event_user_id"),
        UniqueConstraint(
            "event_id",
            "user_id",
            "previous_transaction_id",
            name="uq_compensation_transaction_event_user_previous",
            postgresql_nulls_not_distinct=True,
        ),
        ForeignKeyConstraint(
            columns=["event_id", "user_id", "previous_transaction_id"],
            refcolumns=[
                "user_event_compensation_transaction.event_id",
                "user_event_compensation_transaction.user_id",
                "user_event_compensation_transaction.id",
            ],
            name="fk_compensation_transaction_previous_transaction",
        ),
    )
