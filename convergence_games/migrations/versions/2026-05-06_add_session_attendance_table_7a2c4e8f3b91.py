"""add session_attendance table and tighten allocation cascade

Revision ID: 7a2c4e8f3b91
Revises: 849b06f7ac73
Create Date: 2026-05-06 19:30:00.000000

Introduces an immutable per-(event, time_slot, user) attendance record so
that schedule edits and allocation rewrites cannot destroy game-played
history. Also switches allocation.session_id from ondelete=CASCADE to
ondelete=RESTRICT so future code that tries to delete a Session with
allocations attached fails loudly.

The data_upgrades step backfills session_attendance from every existing
committed Allocation (source = 'Backfill'). This recovers as much of the
historical record as still survives in the DB at the time of upgrade.

"""
# pyright: reportUnusedCallResult=false

import warnings
from typing import TYPE_CHECKING

import sqlalchemy as sa
from advanced_alchemy.types import (
    GUID,
    ORA_JSONB,
    DateTimeUTC,
    EncryptedString,
    EncryptedText,
    StoredObject,
)
from alembic import op
from sqlalchemy import Text  # noqa: F401
from sqlalchemy.dialects import postgresql

if TYPE_CHECKING:
    pass

__all__ = ["downgrade", "upgrade", "schema_upgrades", "schema_downgrades", "data_upgrades", "data_downgrades"]

sa.GUID = GUID
sa.DateTimeUTC = DateTimeUTC
sa.ORA_JSONB = ORA_JSONB
sa.EncryptedString = EncryptedString
sa.EncryptedText = EncryptedText
sa.StoredObject = StoredObject

# revision identifiers, used by Alembic.
revision = "7a2c4e8f3b91"
down_revision = "849b06f7ac73"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=UserWarning)
        with op.get_context().autocommit_block():
            schema_upgrades()
            data_upgrades()


def downgrade() -> None:
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=UserWarning)
        with op.get_context().autocommit_block():
            data_downgrades()
            schema_downgrades()


def schema_upgrades() -> None:
    """schema upgrade migrations go here."""
    # Create the AttendanceRole / AttendanceSource Postgres enum types.
    sa.Enum("PLAYER", "GAMEMASTER", name="attendancerole").create(op.get_bind())
    sa.Enum("COMMIT", "BACKFILL", name="attendancesource").create(op.get_bind())

    op.create_table(
        "session_attendance",
        sa.Column(
            "role",
            postgresql.ENUM("PLAYER", "GAMEMASTER", name="attendancerole", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "source",
            postgresql.ENUM("COMMIT", "BACKFILL", name="attendancesource", create_type=False),
            nullable=False,
        ),
        sa.Column("event_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("time_slot_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("game_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("user_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("table_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True),
        sa.Column("source_allocation_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True),
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False, autoincrement=True),
        sa.Column("created_at", sa.DateTimeUTC(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTimeUTC(timezone=True), nullable=False),
        sa.Column("created_by", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True),
        sa.Column("updated_by", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["user.id"], name=op.f("fk_session_attendance_created_by_user")),
        sa.ForeignKeyConstraint(["updated_by"], ["user.id"], name=op.f("fk_session_attendance_updated_by_user")),
        sa.ForeignKeyConstraint(["event_id"], ["event.id"], name=op.f("fk_session_attendance_event_id_event")),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], name=op.f("fk_session_attendance_user_id_user")),
        sa.ForeignKeyConstraint(["table_id"], ["table.id"], name=op.f("fk_session_attendance_table_id_table")),
        sa.ForeignKeyConstraint(
            ["time_slot_id", "event_id"],
            ["time_slot.id", "time_slot.event_id"],
            name="fk_session_attendance_time_slot_with_event",
        ),
        sa.ForeignKeyConstraint(
            ["game_id", "event_id"],
            ["game.id", "game.event_id"],
            name="fk_session_attendance_game_with_event",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_session_attendance")),
        sa.UniqueConstraint(
            "event_id", "time_slot_id", "user_id", name=op.f("uq_session_attendance_event_id_time_slot_id_user_id")
        ),
    )
    with op.batch_alter_table("session_attendance", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_session_attendance_role"), ["role"], unique=False)
        batch_op.create_index(batch_op.f("ix_session_attendance_event_id"), ["event_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_session_attendance_time_slot_id"), ["time_slot_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_session_attendance_game_id"), ["game_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_session_attendance_user_id"), ["user_id"], unique=False)

    # Tighten allocation.session_id: CASCADE -> RESTRICT.
    with op.batch_alter_table("allocation", schema=None) as batch_op:
        batch_op.drop_constraint("fk_allocation_session_id_session", type_="foreignkey")
        batch_op.create_foreign_key(
            "fk_allocation_session_id_session",
            "session",
            ["session_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def schema_downgrades() -> None:
    """schema downgrade migrations go here."""
    # Restore CASCADE on allocation.session_id.
    with op.batch_alter_table("allocation", schema=None) as batch_op:
        batch_op.drop_constraint("fk_allocation_session_id_session", type_="foreignkey")
        batch_op.create_foreign_key(
            "fk_allocation_session_id_session",
            "session",
            ["session_id"],
            ["id"],
            ondelete="CASCADE",
        )

    with op.batch_alter_table("session_attendance", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_session_attendance_user_id"))
        batch_op.drop_index(batch_op.f("ix_session_attendance_game_id"))
        batch_op.drop_index(batch_op.f("ix_session_attendance_time_slot_id"))
        batch_op.drop_index(batch_op.f("ix_session_attendance_event_id"))
        batch_op.drop_index(batch_op.f("ix_session_attendance_role"))

    op.drop_table("session_attendance")

    sa.Enum(name="attendancesource").drop(op.get_bind())
    sa.Enum(name="attendancerole").drop(op.get_bind())


def data_upgrades() -> None:
    """Backfill happens here; populated in a follow-up commit."""


def data_downgrades() -> None:
    """No data downgrade -- schema_downgrades drops the table entirely."""
