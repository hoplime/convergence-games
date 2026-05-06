"""add user_session table

Revision ID: b2606ec85fe1
Revises: 849b06f7ac73
Create Date: 2026-05-06 20:00:00.000000

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
revision = "b2606ec85fe1"
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
    op.create_table(
        "user_session",
        sa.Column("jti", sa.String(), nullable=False),
        sa.Column("family_id", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTimeUTC(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTimeUTC(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTimeUTC(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.String(), nullable=True),
        sa.Column("user_agent", sa.String(), nullable=True),
        sa.Column("user_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False, autoincrement=True),
        sa.Column("created_at", sa.DateTimeUTC(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTimeUTC(timezone=True), nullable=False),
        sa.Column("created_by", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True),
        sa.Column("updated_by", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["user.id"], name=op.f("fk_user_session_created_by_user")),
        sa.ForeignKeyConstraint(["updated_by"], ["user.id"], name=op.f("fk_user_session_updated_by_user")),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], name=op.f("fk_user_session_user_id_user")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_session")),
        sa.UniqueConstraint("jti", name=op.f("uq_user_session_jti")),
    )
    with op.batch_alter_table("user_session", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_user_session_family_id"), ["family_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_user_session_jti"), ["jti"], unique=True)
        batch_op.create_index(batch_op.f("ix_user_session_user_id"), ["user_id"], unique=False)


def schema_downgrades() -> None:
    """schema downgrade migrations go here."""
    with op.batch_alter_table("user_session", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_user_session_user_id"))
        batch_op.drop_index(batch_op.f("ix_user_session_jti"))
        batch_op.drop_index(batch_op.f("ix_user_session_family_id"))

    op.drop_table("user_session")


def data_upgrades() -> None:
    """Add any optional data upgrade migrations here!"""


def data_downgrades() -> None:
    """Add any optional data downgrade migrations here!"""
