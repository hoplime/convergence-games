"""add slug columns to event, game, user

Revision ID: 8d64f1978eda
Revises: 849b06f7ac73
Create Date: 2026-05-07 00:00:00.000000

"""
# pyright: reportUnusedCallResult=false

import random
import string
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
from advanced_alchemy.utils.text import slugify
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
revision = "8d64f1978eda"
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


_SUFFIX_LENGTH = 4
_SUFFIX_ALPHABET = string.ascii_lowercase + string.digits


def _random_suffix() -> str:
    return "".join(random.choices(_SUFFIX_ALPHABET, k=_SUFFIX_LENGTH))  # noqa: S311


def _resolve_slug(base: str, used: set[str]) -> str:
    candidate = base
    while candidate in used:
        candidate = f"{base}-{_random_suffix()}"
    used.add(candidate)
    return candidate


def schema_upgrades() -> None:
    """schema upgrade migrations go here."""
    # Add nullable slug columns first so the data backfill can populate them.
    with op.batch_alter_table("event", schema=None) as batch_op:
        batch_op.add_column(sa.Column("slug", sa.String(length=100), nullable=True))
    with op.batch_alter_table("game", schema=None) as batch_op:
        batch_op.add_column(sa.Column("slug", sa.String(length=100), nullable=True))
    with op.batch_alter_table('"user"', schema=None) as batch_op:
        batch_op.add_column(sa.Column("slug", sa.String(length=100), nullable=True))


def schema_downgrades() -> None:
    """schema downgrade migrations go here."""
    with op.batch_alter_table('"user"', schema=None) as batch_op:
        batch_op.drop_index("ix_user_slug_unique")
        batch_op.drop_constraint("uq_user_slug", type_="unique")
        batch_op.drop_column("slug")
    with op.batch_alter_table("game", schema=None) as batch_op:
        batch_op.drop_index("ix_game_event_slug_unique")
        batch_op.drop_constraint("uq_game_event_slug", type_="unique")
        batch_op.drop_column("slug")
    with op.batch_alter_table("event", schema=None) as batch_op:
        batch_op.drop_index("ix_event_slug_unique")
        batch_op.drop_constraint("uq_event_slug", type_="unique")
        batch_op.drop_column("slug")


def data_upgrades() -> None:
    """Backfill slugs for existing rows, then enforce NOT NULL + unique constraints."""
    bind = op.get_bind()

    # Event: slug from name, table-wide unique.
    used_event_slugs: set[str] = set()
    events = bind.execute(sa.text("SELECT id, name FROM event ORDER BY id")).fetchall()
    for row in events:
        base = slugify(row.name or "") or "event"
        slug = _resolve_slug(base, used_event_slugs)
        bind.execute(
            sa.text("UPDATE event SET slug = :slug WHERE id = :id"),
            {"slug": slug, "id": row.id},
        )

    # User: slug from "first_name last_name", placeholder if both empty.
    used_user_slugs: set[str] = set()
    users = bind.execute(sa.text('SELECT id, first_name, last_name FROM "user" ORDER BY id')).fetchall()
    for row in users:
        full_name = f"{row.first_name or ''} {row.last_name or ''}".strip()
        if full_name:
            base = slugify(full_name) or "user"
        else:
            # Profile not yet completed — assign a placeholder slug.
            base = f"user-{_random_suffix()}{_random_suffix()}"
        slug = _resolve_slug(base, used_user_slugs)
        bind.execute(
            sa.text('UPDATE "user" SET slug = :slug WHERE id = :id'),
            {"slug": slug, "id": row.id},
        )

    # Game: slug from name, scoped per event_id.
    used_game_slugs_by_event: dict[int, set[str]] = {}
    games = bind.execute(sa.text("SELECT id, name, event_id FROM game ORDER BY event_id, id")).fetchall()
    for row in games:
        used = used_game_slugs_by_event.setdefault(row.event_id, set())
        base = slugify(row.name or "") or "game"
        slug = _resolve_slug(base, used)
        bind.execute(
            sa.text("UPDATE game SET slug = :slug WHERE id = :id"),
            {"slug": slug, "id": row.id},
        )

    # Now enforce NOT NULL and add unique constraints/indexes.
    with op.batch_alter_table("event", schema=None) as batch_op:
        batch_op.alter_column("slug", existing_type=sa.String(length=100), nullable=False)
        batch_op.create_unique_constraint("uq_event_slug", ["slug"])
        batch_op.create_index("ix_event_slug_unique", ["slug"], unique=True)
    with op.batch_alter_table('"user"', schema=None) as batch_op:
        batch_op.alter_column("slug", existing_type=sa.String(length=100), nullable=False)
        batch_op.create_unique_constraint("uq_user_slug", ["slug"])
        batch_op.create_index("ix_user_slug_unique", ["slug"], unique=True)
    with op.batch_alter_table("game", schema=None) as batch_op:
        batch_op.alter_column("slug", existing_type=sa.String(length=100), nullable=False)
        batch_op.create_unique_constraint("uq_game_event_slug", ["event_id", "slug"])
        batch_op.create_index("ix_game_event_slug_unique", ["event_id", "slug"], unique=True)


def data_downgrades() -> None:
    """Add any optional data downgrade migrations here!"""
