# pyright: reportImportCycles=false
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import and_, select
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, relationship

from ._base import Base

# These are used as real objects (not string-based relationship args) below, in both
# `parties`/`party_user_links` (secondary=PartyUserLink.__table__) and `__mapper_args__`
# (which builds relationship() objects against UserEventD20Transaction/UserEventCompensationTransaction
# directly) - both need runtime imports, not just TYPE_CHECKING ones.
from ._party_user_link import PartyUserLink
from ._user_event_compensation_transaction import UserEventCompensationTransaction
from ._user_event_d20_transaction import UserEventD20Transaction

if TYPE_CHECKING:
    from ._allocation import Allocation
    from ._game import Game
    from ._party import Party
    from ._user_checkin_status import UserCheckinStatus
    from ._user_event_role import UserEventRole
    from ._user_game_played import UserGamePlayed
    from ._user_game_preference import UserGamePreference
    from ._user_login import UserLogin


class User(Base):
    first_name: Mapped[str] = mapped_column(index=True, default="")
    last_name: Mapped[str] = mapped_column(index=True, default="")
    description: Mapped[str] = mapped_column(default="")
    over_18: Mapped[bool] = mapped_column(default=False)

    # Relationships
    games: Mapped[list[Game]] = relationship(
        back_populates="gamemaster", primaryjoin="User.id == Game.gamemaster_id", lazy="noload"
    )
    logins: Mapped[list[UserLogin]] = relationship(
        back_populates="user", primaryjoin="User.id == UserLogin.user_id", lazy="noload"
    )
    event_roles: Mapped[list[UserEventRole]] = relationship(
        back_populates="user", primaryjoin="User.id == UserEventRole.user_id", lazy="noload"
    )
    current_game_preferences: Mapped[list[UserGamePreference]] = relationship(
        primaryjoin="and_(User.id == UserGamePreference.user_id, UserGamePreference.frozen_at_time_slot_id.is_(None))",
        lazy="noload",
        viewonly=True,
    )
    all_game_preferences: Mapped[list[UserGamePreference]] = relationship(
        back_populates="user",
        primaryjoin="User.id == UserGamePreference.user_id",
        lazy="noload",
        viewonly=True,
    )
    parties: Mapped[list[Party]] = relationship(
        back_populates="members",
        secondary=PartyUserLink.__table__,
        primaryjoin="User.id == PartyUserLink.user_id",
        secondaryjoin="Party.id == PartyUserLink.party_id",
        viewonly=True,
        lazy="noload",
    )
    d20_transactions: Mapped[list[UserEventD20Transaction]] = relationship(
        back_populates="user", primaryjoin="User.id == UserEventD20Transaction.user_id", lazy="noload"
    )
    compensation_transactions: Mapped[list[UserEventCompensationTransaction]] = relationship(
        back_populates="user", primaryjoin="User.id == UserEventCompensationTransaction.user_id", lazy="noload"
    )
    checkin_statuses: Mapped[list[UserCheckinStatus]] = relationship(
        back_populates="user", primaryjoin="User.id == UserCheckinStatus.user_id", lazy="noload"
    )
    allocations: Mapped[list[Allocation]] = relationship(
        back_populates="party_leader", primaryjoin="User.id == Allocation.party_leader_id", lazy="noload"
    )
    games_played: Mapped[list[UserGamePlayed]] = relationship(
        back_populates="user", primaryjoin="User.id == UserGamePlayed.user_id", lazy="noload"
    )

    @declared_attr.directive
    @classmethod
    def __mapper_args__(cls):
        # TODO: These are BUGGED when it comes to further filtering by event ID etc - don't use
        # https://stackoverflow.com/a/73517812
        latest_d20_transaction = relationship(
            UserEventD20Transaction,
            primaryjoin=and_(
                UserEventD20Transaction.id
                == (
                    select(UserEventD20Transaction.id)
                    .where(UserEventD20Transaction.user_id == cls.id)
                    .order_by(UserEventD20Transaction.id.desc())
                    .limit(1)
                    .correlate(cls.__table__)
                    .scalar_subquery()
                ),
                UserEventD20Transaction.user_id == cls.id,
            ),
            uselist=False,
            viewonly=True,
            lazy="noload",
        )

        latest_compensation_transaction = relationship(
            UserEventCompensationTransaction,
            primaryjoin=and_(
                UserEventCompensationTransaction.id
                == (
                    select(UserEventCompensationTransaction.id)
                    .where(UserEventCompensationTransaction.user_id == cls.id)
                    .order_by(UserEventCompensationTransaction.id.desc())
                    .limit(1)
                    .correlate(cls.__table__)
                    .scalar_subquery()
                ),
                UserEventCompensationTransaction.user_id == cls.id,
            ),
            uselist=False,
            viewonly=True,
            lazy="noload",
        )

        return {
            "properties": {
                "latest_d20_transaction": latest_d20_transaction,
                "latest_compensation_transaction": latest_compensation_transaction,
            }
        }

    if TYPE_CHECKING:
        latest_d20_transaction: Mapped[UserEventD20Transaction | None] = relationship()
        latest_compensation_transaction: Mapped[UserEventCompensationTransaction | None] = relationship()

    # Association Proxy Relationships
    party_user_links: Mapped[list[PartyUserLink]] = relationship(
        back_populates="user", primaryjoin="User.id == PartyUserLink.user_id", lazy="noload"
    )

    @property
    def is_profile_setup(self) -> bool:
        return self.first_name != ""

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}" if self.last_name else self.first_name

    @property
    def initials(self) -> str:
        initials = self.first_name[0].upper()
        if self.last_name:
            initials += self.last_name[0].upper()
        return initials
