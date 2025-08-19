from __future__ import annotations

import datetime as dt
from base64 import urlsafe_b64decode, urlsafe_b64encode
from typing import TYPE_CHECKING, Any
from uuid import UUID

from advanced_alchemy.base import BigIntAuditBase
from advanced_alchemy.types import DateTimeUTC
from sqlalchemy import (
    Connection,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    UniqueConstraint,
    and_,
    select,
)
from sqlalchemy import event as sqla_event
from sqlalchemy.orm import Mapped, Mapper, declared_attr, mapped_column, relationship, validates

from convergence_games.app.context import user_id_ctx
from convergence_games.db.enums import (
    GameActivityRequirement,
    GameClassification,
    GameCoreActivity,
    GameCrunch,
    GameEquipmentRequirement,
    GameKSP,
    GameRoomRequirement,
    GameTableSizeRequirement,
    GameTone,
    LoginProvider,
    Role,
    RoomFacility,
    SubmissionStatus,
    TableFacility,
    TableSize,
    TimeSlotStatus,
    UserGamePreferenceValue,
)


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


# Game Information Link Models
class GameGenreLink(Base):
    game_id: Mapped[int] = mapped_column(ForeignKey("game.id"), primary_key=True)
    genre_id: Mapped[int] = mapped_column(ForeignKey("genre.id"), primary_key=True)

    game: Mapped[Game] = relationship(back_populates="genre_links", lazy="noload")
    genre: Mapped[Genre] = relationship(back_populates="game_links", lazy="noload")

    __table_args__ = (UniqueConstraint("game_id", "genre_id"),)


class GameContentWarningLink(Base):
    game_id: Mapped[int] = mapped_column(ForeignKey("game.id"), primary_key=True)
    content_warning_id: Mapped[int] = mapped_column(ForeignKey("content_warning.id"), primary_key=True)

    game: Mapped[Game] = relationship(back_populates="content_warning_links", lazy="noload")
    content_warning: Mapped[ContentWarning] = relationship(back_populates="game_links", lazy="noload")

    __table_args__ = (UniqueConstraint("game_id", "content_warning_id"),)


class GameImageLink(Base):
    image_id: Mapped[int] = mapped_column(ForeignKey("image.id"), primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("game.id"), primary_key=True)
    sort_order: Mapped[int] = mapped_column(default=0)

    image: Mapped[Image] = relationship(back_populates="game_links", lazy="noload")
    game: Mapped[Game] = relationship(back_populates="image_links", lazy="noload")


class Image(Base):
    lookup_key: Mapped[UUID] = mapped_column(index=True, unique=True)

    # Relationships
    games: Mapped[list[Game]] = relationship(
        back_populates="images",
        secondary=GameImageLink.__table__,
        viewonly=True,
        lazy="noload",
    )

    # Association Proxy Relationships
    game_links: Mapped[list[GameImageLink]] = relationship(back_populates="image", lazy="noload")


# Game Information Models
class Event(Base):
    name: Mapped[str] = mapped_column(index=True, unique=True)
    description: Mapped[str] = mapped_column(default="")
    start_date: Mapped[dt.datetime] = mapped_column(DateTimeUTC(timezone=True), index=True)
    end_date: Mapped[dt.datetime] = mapped_column(DateTimeUTC(timezone=True), index=True)
    timezone: Mapped[str] = mapped_column(default="Pacific/Auckland")
    max_party_size: Mapped[int] = mapped_column(default=3, server_default="3")

    # Relationships
    rooms: Mapped[list[Room]] = relationship(back_populates="event", lazy="noload")
    tables: Mapped[list[Table]] = relationship(back_populates="event", lazy="noload")
    sessions: Mapped[list[Session]] = relationship(back_populates="event", lazy="noload", cascade="all, delete-orphan")
    time_slots: Mapped[list[TimeSlot]] = relationship(back_populates="event", lazy="noload")
    games: Mapped[list[Game]] = relationship(back_populates="event", lazy="noload")
    user_roles: Mapped[list[UserEventRole]] = relationship(back_populates="event", lazy="noload")
    game_requirements: Mapped[list[GameRequirement]] = relationship(back_populates="event", lazy="noload")
    game_requirement_time_slot_links: Mapped[list[GameRequirementTimeSlotLink]] = relationship(
        back_populates="event", lazy="noload"
    )
    d20_transactions: Mapped[list[UserEventD20Transaction]] = relationship(back_populates="event", lazy="noload")
    compensation_transactions: Mapped[list[UserEventCompensationTransaction]] = relationship(
        back_populates="event", lazy="noload"
    )


class System(Base):
    name: Mapped[str] = mapped_column(index=True, unique=True)
    description: Mapped[str] = mapped_column(default="")
    submission_status: Mapped[SubmissionStatus] = mapped_column(
        Enum(SubmissionStatus), default=SubmissionStatus.SUBMITTED, index=True
    )

    # Relationships
    games: Mapped[list[Game]] = relationship(back_populates="system", lazy="noload")
    aliases: Mapped[list[SystemAlias]] = relationship(back_populates="system", lazy="noload")


class SystemAlias(Base):
    name: Mapped[str] = mapped_column(index=True, unique=True)
    system_id: Mapped[int] = mapped_column(ForeignKey("system.id"), index=True)

    # Relationships
    system: Mapped[System] = relationship(back_populates="aliases", lazy="noload")

    __table_args__ = (UniqueConstraint("name", "system_id"),)


class Genre(Base):
    name: Mapped[str] = mapped_column(index=True, unique=True)
    description: Mapped[str] = mapped_column(default="")
    suggested: Mapped[bool] = mapped_column(default=False)
    submission_status: Mapped[SubmissionStatus] = mapped_column(
        Enum(SubmissionStatus), default=SubmissionStatus.SUBMITTED, index=True
    )

    # Relationships
    games: Mapped[list[Game]] = relationship(
        back_populates="genres",
        secondary=GameGenreLink.__table__,
        viewonly=True,
        lazy="noload",
    )

    # Association Proxy Relationships
    game_links: Mapped[list[GameGenreLink]] = relationship(back_populates="genre", lazy="noload")


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


class Game(Base):
    # Description Fields
    name: Mapped[str] = mapped_column(index=True)
    tagline: Mapped[str] = mapped_column(default="")
    description: Mapped[str] = mapped_column(default="")  # TODO: JSON type?

    # Tags
    classification: Mapped[GameClassification] = mapped_column(
        Enum(GameClassification), default=GameClassification.PG, index=True
    )
    crunch: Mapped[GameCrunch] = mapped_column(Enum(GameCrunch), default=GameCrunch.MEDIUM, index=True)
    core_activity: Mapped[GameCoreActivity] = mapped_column(Integer, default=GameCoreActivity.NONE, index=True)
    tone: Mapped[GameTone] = mapped_column(Enum(GameTone), default=GameTone.LIGHT_HEARTED, index=True)

    # Player Count
    player_count_minimum: Mapped[int] = mapped_column()
    player_count_optimum: Mapped[int] = mapped_column()
    player_count_maximum: Mapped[int] = mapped_column()

    # Bonus
    ksps: Mapped[GameKSP] = mapped_column(Integer, default=GameKSP.NONE)
    submission_status: Mapped[SubmissionStatus] = mapped_column(
        Enum(SubmissionStatus), default=SubmissionStatus.SUBMITTED, index=True
    )

    # Foreign Keys
    system_id: Mapped[int] = mapped_column(ForeignKey("system.id"), index=True)
    gamemaster_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id"), index=True)

    # Relationships
    system: Mapped[System] = relationship(back_populates="games", lazy="noload")
    gamemaster: Mapped[User] = relationship(back_populates="games", foreign_keys=gamemaster_id, lazy="noload")
    event: Mapped[Event] = relationship(back_populates="games", lazy="noload")
    game_requirement: Mapped[GameRequirement] = relationship(
        back_populates="game", foreign_keys="GameRequirement.game_id", lazy="noload"
    )
    sessions: Mapped[list[Session]] = relationship(back_populates="game", foreign_keys="Session.game_id", lazy="noload")
    genres: Mapped[list[Genre]] = relationship(
        back_populates="games",
        secondary=GameGenreLink.__table__,
        viewonly=True,
        lazy="noload",
    )
    content_warnings: Mapped[list[ContentWarning]] = relationship(
        back_populates="games",
        secondary=GameContentWarningLink.__table__,
        viewonly=True,
        lazy="noload",
    )
    images: Mapped[list[Image]] = relationship(
        back_populates="games",
        secondary=GameImageLink.__table__,
        viewonly=True,
        lazy="noload",
        order_by=GameImageLink.sort_order,
    )
    user_preferences: Mapped[list[UserGamePreference]] = relationship(back_populates="game", lazy="noload")

    # Association Proxy Relationships
    genre_links: Mapped[list[GameGenreLink]] = relationship(back_populates="game", lazy="noload")
    content_warning_links: Mapped[list[GameContentWarningLink]] = relationship(back_populates="game", lazy="noload")
    image_links: Mapped[list[GameImageLink]] = relationship(back_populates="game", lazy="noload")

    __table_args__ = (
        # This redundant constraint is necessary for the foreign key constraint in Session
        UniqueConstraint("id", "event_id"),
    )


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


class GameRequirement(Base):
    times_to_run: Mapped[int] = mapped_column(default=1)
    scheduling_notes: Mapped[str] = mapped_column(default="")
    table_size_requirement: Mapped[GameTableSizeRequirement] = mapped_column(
        Integer, default=GameTableSizeRequirement.NONE
    )
    table_size_notes: Mapped[str] = mapped_column(default="")
    equipment_requirement: Mapped[GameEquipmentRequirement] = mapped_column(
        Integer, default=GameEquipmentRequirement.NONE
    )
    equipment_notes: Mapped[str] = mapped_column(default="")
    activity_requirement: Mapped[GameActivityRequirement] = mapped_column(Integer, default=GameActivityRequirement.NONE)
    activity_notes: Mapped[str] = mapped_column(default="")
    room_requirement: Mapped[GameRoomRequirement] = mapped_column(Integer, default=GameRoomRequirement.NONE)
    room_notes: Mapped[str] = mapped_column(default="")

    # Foreign Keys
    game_id: Mapped[int] = mapped_column(ForeignKey("game.id"), index=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("event.id"), index=True
    )  # Logically redundant, but necessary for constraints

    # Relationships
    game: Mapped[Game] = relationship(
        back_populates="game_requirement", foreign_keys=game_id, single_parent=True, lazy="noload"
    )
    event: Mapped[Event] = relationship(back_populates="game_requirements", foreign_keys=event_id, lazy="noload")
    available_time_slots: Mapped[list[TimeSlot]] = relationship(
        back_populates="game_requirements",
        secondary="game_requirement_time_slot_link",
        primaryjoin="GameRequirement.id == GameRequirementTimeSlotLink.game_requirement_id",
        secondaryjoin="TimeSlot.id == GameRequirementTimeSlotLink.time_slot_id",
        viewonly=True,
        lazy="noload",
    )

    # Association Proxy Relationships
    time_slot_links: Mapped[list[GameRequirementTimeSlotLink]] = relationship(
        back_populates="game_requirement",
        primaryjoin="GameRequirement.id == GameRequirementTimeSlotLink.game_requirement_id",
        lazy="noload",
    )

    __table_args__ = (
        UniqueConstraint("game_id"),
        # This redundant constraint is necessary for the foreign key constraint in Session
        UniqueConstraint("id", "event_id"),
        foreign_key_constraint_with_event("game_requirement", "game"),
    )


@sqla_event.listens_for(GameRequirement, "before_insert")
def game_requirement_before_insert(mapper: Mapper[Any], connection: Connection, target: GameRequirement):
    if target.event_id is None:
        target.event_id = target.game.event_id


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


# Timetable Information Models
class TimeSlot(Base):
    name: Mapped[str] = mapped_column(default="")
    start_time: Mapped[dt.datetime] = mapped_column(DateTimeUTC(timezone=True))
    end_time: Mapped[dt.datetime] = mapped_column(DateTimeUTC(timezone=True))
    checkin_open_time: Mapped[dt.datetime | None] = mapped_column(DateTimeUTC(timezone=True), nullable=True)
    status: Mapped[TimeSlotStatus] = mapped_column(
        Enum(TimeSlotStatus), default=TimeSlotStatus.PRE_ALLOCATION, server_default="PRE_ALLOCATION"
    )

    # Foreign Keys
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id"), index=True)

    # Relationships
    event: Mapped[Event] = relationship(back_populates="time_slots", lazy="noload")
    sessions: Mapped[list[Session]] = relationship(
        back_populates="time_slot", foreign_keys="Session.time_slot_id", lazy="noload"
    )
    game_requirements: Mapped[list[GameRequirement]] = relationship(
        back_populates="available_time_slots",
        secondary=GameRequirementTimeSlotLink.__table__,
        primaryjoin="TimeSlot.id == GameRequirementTimeSlotLink.time_slot_id",
        secondaryjoin="GameRequirement.id == GameRequirementTimeSlotLink.game_requirement_id",
        viewonly=True,
        lazy="noload",
    )
    parties: Mapped[list[Party]] = relationship(
        back_populates="time_slot", foreign_keys="Party.time_slot_id", lazy="noload"
    )
    d20_transactions: Mapped[list[UserEventD20Transaction]] = relationship(
        back_populates="associated_time_slot",
        foreign_keys="UserEventD20Transaction.associated_time_slot_id",
        lazy="noload",
    )
    compensation_transactions: Mapped[list[UserEventCompensationTransaction]] = relationship(
        back_populates="associated_time_slot",
        foreign_keys="UserEventCompensationTransaction.associated_time_slot_id",
        lazy="noload",
    )
    checkin_statuses: Mapped[list[UserCheckinStatus]] = relationship(back_populates="time_slot", lazy="noload")

    # Association Proxy Relationships
    game_requirement_links: Mapped[list[GameRequirementTimeSlotLink]] = relationship(
        back_populates="time_slot",
        primaryjoin="TimeSlot.id == GameRequirementTimeSlotLink.time_slot_id",
        lazy="noload",
    )

    __table_args__ = (
        # This redundant constraint is necessary for the foreign key constraint in Session
        UniqueConstraint("id", "event_id"),
    )

    @property
    def duration(self) -> dt.timedelta:
        return self.end_time - self.start_time


class Room(Base):
    name: Mapped[str] = mapped_column(default="")
    description: Mapped[str] = mapped_column(default="")
    facilities: Mapped[RoomFacility] = mapped_column(Integer, default=RoomFacility.NONE, server_default="0")

    # Foreign Keys
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id"), index=True)

    # Relationships
    event: Mapped[Event] = relationship(back_populates="rooms", lazy="noload")
    tables: Mapped[list[Table]] = relationship(back_populates="room", foreign_keys="Table.room_id", lazy="noload")

    __table_args__ = (
        # This redundant constraint is necessary for the foreign key constraint in Session
        UniqueConstraint("id", "event_id"),
    )


class Table(Base):
    name: Mapped[str] = mapped_column(default="")
    facilities: Mapped[TableFacility] = mapped_column(Integer, default=TableFacility.NONE, server_default="0")
    size: Mapped[TableSize] = mapped_column(
        Enum(TableSize), default=TableSize.SMALL, server_default="SMALL", index=True
    )

    # Foreign Keys
    room_id: Mapped[int] = mapped_column(ForeignKey("room.id"), index=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("event.id"), index=True
    )  # Logically redundant, but necessary for constraints

    # Relationships
    room: Mapped[Room] = relationship(back_populates="tables", foreign_keys=room_id, lazy="noload")
    event: Mapped[Event] = relationship(back_populates="tables", lazy="noload")
    sessions: Mapped[list[Session]] = relationship(
        back_populates="table", foreign_keys="Session.table_id", lazy="noload"
    )

    __table_args__ = (
        # This redundant constraint is necessary for the foreign key constraint in Session
        UniqueConstraint("id", "event_id"),
        foreign_key_constraint_with_event("table", "room"),
    )


@sqla_event.listens_for(Table, "before_insert")
def table_before_insert(mapper: Mapper[Any], connection: Connection, target: Table):
    if target.event_id is None:
        target.event_id = target.room.event_id


class Session(Base):
    committed: Mapped[bool] = mapped_column(default=False, server_default="0")

    # Foreign Keys
    game_id: Mapped[int] = mapped_column(ForeignKey("game.id"), index=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("table.id"), index=True)
    time_slot_id: Mapped[int] = mapped_column(ForeignKey("time_slot.id"), index=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("event.id"), index=True
    )  # Logically redundant, but necessary for constraints

    # Relationships
    game: Mapped[Game] = relationship(back_populates="sessions", foreign_keys=game_id, lazy="noload")
    table: Mapped[Table] = relationship(back_populates="sessions", foreign_keys=table_id, lazy="noload")
    time_slot: Mapped[TimeSlot] = relationship(back_populates="sessions", foreign_keys=time_slot_id, lazy="noload")
    event: Mapped[Event] = relationship(back_populates="sessions", lazy="noload")

    __table_args__ = (
        # https://dba.stackexchange.com/a/58972
        # https://stackoverflow.com/a/63922398
        # These constraints ensure that the Game, Table and TimeSlot are part of the same Event
        foreign_key_constraint_with_event("session", "game"),
        foreign_key_constraint_with_event("session", "table"),
        foreign_key_constraint_with_event("session", "time_slot"),
    )


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


# User Information Models


class UserEventD20Transaction(Base):
    current_balance: Mapped[int] = mapped_column(default=0)
    previous_balance: Mapped[int] = mapped_column(default=0)
    delta: Mapped[int] = mapped_column(default=0)

    # Foreign Keys
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)
    previous_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_event_d20_transaction.id"), index=True, nullable=True
    )
    associated_time_slot_id: Mapped[int | None] = mapped_column(ForeignKey("time_slot.id"), index=True, nullable=True)

    # Relationships
    event: Mapped[Event] = relationship(back_populates="d20_transactions", lazy="noload")
    user: Mapped[User] = relationship(
        back_populates="d20_transactions", primaryjoin="User.id == UserEventD20Transaction.user_id", lazy="noload"
    )
    previous_transaction: Mapped[UserEventD20Transaction | None] = relationship(
        foreign_keys=[event_id, user_id, previous_transaction_id],
        remote_side="UserEventD20Transaction.event_id, UserEventD20Transaction.user_id, UserEventD20Transaction.id",
        back_populates="next_transaction",
        lazy="noload",
        viewonly=True,
    )
    next_transaction: Mapped[UserEventD20Transaction | None] = relationship(
        foreign_keys="UserEventD20Transaction.event_id, UserEventD20Transaction.user_id, UserEventD20Transaction.id",
        remote_side=[event_id, user_id, previous_transaction_id],
        back_populates="previous_transaction",
        lazy="noload",
        viewonly=True,
    )
    associated_time_slot: Mapped[TimeSlot | None] = relationship(back_populates="d20_transactions", lazy="noload")

    __table_args__ = (
        UniqueConstraint("previous_transaction_id"),
        # We need to make sure that all transactions in a chain point to the same event and user
        UniqueConstraint("event_id", "user_id", "id", name="uq_d20_transaction_event_user_id"),
        UniqueConstraint(
            "event_id", "user_id", "previous_transaction_id", name="uq_d20_transaction_event_user_previous"
        ),
        ForeignKeyConstraint(
            columns=["event_id", "user_id", "previous_transaction_id"],
            refcolumns=[
                "user_event_d20_transaction.event_id",
                "user_event_d20_transaction.user_id",
                "user_event_d20_transaction.id",
            ],
            name="fk_d20_transaction_previous_transaction",
        ),
    )


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
            "event_id", "user_id", "previous_transaction_id", name="uq_compensation_transaction_event_user_previous"
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
    game_preferences: Mapped[list[UserGamePreference]] = relationship(
        back_populates="user", primaryjoin="User.id == UserGamePreference.user_id", lazy="noload"
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

    @declared_attr.directive
    @classmethod
    def __mapper_args__(cls):
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


class UserEventRole(Base):
    role: Mapped[Role] = mapped_column(Enum(Role), index=True)

    # Foreign Keys
    event_id: Mapped[int | None] = mapped_column(ForeignKey("event.id"), index=True, nullable=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)

    # Relationships
    event: Mapped[Event] = relationship(back_populates="user_roles", lazy="noload")
    user: Mapped[User] = relationship(
        back_populates="event_roles", primaryjoin="User.id == UserEventRole.user_id", lazy="noload"
    )

    __table_args__ = (UniqueConstraint("event_id", "user_id", "role"),)


class UserGamePreference(Base):
    preference: Mapped[UserGamePreferenceValue] = mapped_column(
        Enum(UserGamePreferenceValue, validate_strings=True), index=True, nullable=False
    )

    # Foreign Keys
    game_id: Mapped[int] = mapped_column(ForeignKey("game.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), primary_key=True)

    # Relationships
    game: Mapped[Game] = relationship(back_populates="user_preferences", lazy="noload")
    user: Mapped[User] = relationship(
        back_populates="game_preferences", primaryjoin="User.id == UserGamePreference.user_id", lazy="noload"
    )

    __table_args__ = (UniqueConstraint("game_id", "user_id"),)


class UserCheckinStatus(Base):
    checked_in: Mapped[bool] = mapped_column(default=False)

    # Foreign Keys
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), primary_key=True)
    time_slot_id: Mapped[int] = mapped_column(ForeignKey("time_slot.id"), primary_key=True)

    # Relationships
    user: Mapped[User] = relationship(
        back_populates="checkin_statuses", primaryjoin="User.id == UserCheckinStatus.user_id", lazy="noload"
    )
    time_slot: Mapped[TimeSlot] = relationship(
        back_populates="checkin_statuses", foreign_keys=time_slot_id, lazy="noload"
    )

    __table_args__ = (UniqueConstraint("user_id", "time_slot_id"),)


class UserLogin(Base):
    provider: Mapped[LoginProvider] = mapped_column(Enum(LoginProvider, validate_strings=True), index=True)
    provider_user_id: Mapped[str] = mapped_column(index=True)
    provider_email: Mapped[str | None] = mapped_column(index=True)

    # Foreign Keys
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)

    # Relationships
    user: Mapped[User] = relationship(back_populates="logins", foreign_keys=user_id, lazy="noload")

    __table_args__ = (UniqueConstraint("provider", "provider_user_id"), UniqueConstraint("user_id", "provider"))


class UserEmailVerificationCode(Base):
    code: Mapped[str] = mapped_column(index=True)
    email: Mapped[str] = mapped_column(index=True)
    expires_at: Mapped[dt.datetime] = mapped_column(
        DateTimeUTC(timezone=True),
        default=lambda: dt.datetime.now(tz=dt.timezone.utc) + dt.timedelta(hours=4),
    )

    @validates("expires_at")
    def validate_tz_info(self, _: str, value: dt.datetime) -> dt.datetime:
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt.timezone.utc)
        return value

    @staticmethod
    def generate_magic_link_code(code: str, email: str) -> str:
        # Encode the code and email in base64
        code = f"{code}:{email}"
        encoded_code = urlsafe_b64encode(code.encode()).decode()
        return encoded_code

    @staticmethod
    def decode_magic_link_code(magic_link_code: str) -> tuple[str, str]:
        # Decode the code from base64
        decoded_code = urlsafe_b64decode(magic_link_code.encode()).decode()
        code, email = decoded_code.split(":", 1)
        return code, email
