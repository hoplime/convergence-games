"""Import JSON fixture files into the database.

Usage:
    uv run python scripts/import_fixtures.py [fixture_dir]

Defaults to fixtures/local_db_backup if no directory is specified.
Expects the database to already have the schema (run migrations first).
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
from pathlib import Path
from typing import cast

from sqlalchemy import Table, text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from sqlalchemy.sql.type_api import TypeDecorator
from sqlalchemy.types import DateTime

from convergence_games.db.models import Base
from convergence_games.settings import SETTINGS

# Insertion order respects foreign key dependencies.
# Root tables first, then tables that depend on them, etc.
TABLE_ORDER = [
    # Root tables (no FKs)
    "user",
    "event",
    "system",
    "genre",
    "content_warning",
    "image",
    "user_email_verification_code",
    # Depends on root tables
    "system_alias",
    "room",
    "time_slot",
    "game",
    "user_login",
    "user_event_role",
    # Depends on second tier
    "table",
    "game_requirement",
    "party",
    "user_game_played",
    "user_checkin_status",
    # Depends on third tier
    "game_requirement_time_slot_link",
    "game_genre_link",
    "game_content_warning_link",
    "game_image_link",
    "session",
    "party_user_link",
    # Depends on fourth tier
    "allocation",
    "user_game_preference",
    # Self-referential (2-pass insert)
    "user_event_d20_transaction",
    "user_event_compensation_transaction",
]

# Tables with a self-referential FK that needs a 2-pass insert
SELF_REFERENTIAL_TABLES = {
    "user_event_d20_transaction": "previous_transaction_id",
    "user_event_compensation_transaction": "previous_transaction_id",
}


def _is_datetime_column(col_type: object) -> bool:
    """Check if a column type is DateTime, including TypeDecorator wrappers like DateTimeUTC."""
    if isinstance(col_type, DateTime):
        return True
    if isinstance(col_type, TypeDecorator):
        return isinstance(col_type.impl, DateTime)
    return False


def get_datetime_columns(sa_table: Table) -> set[str]:
    """Get column names that use DateTime types (including DateTimeUTC from advanced_alchemy)."""
    return {col.name for col in sa_table.columns if _is_datetime_column(col.type)}


def parse_datetime_columns(row: dict[str, object], datetime_cols: set[str]) -> dict[str, object]:
    """Parse ISO 8601 datetime strings into datetime objects for DateTime-typed columns."""
    return {
        key: dt.datetime.fromisoformat(value) if key in datetime_cols and isinstance(value, str) else value
        for key, value in row.items()
    }


async def import_table(conn: AsyncConnection, table_name: str, fixture_dir: Path) -> None:
    file_path = fixture_dir / f"{table_name}.json"
    if not file_path.exists():
        print(f"  Skipping {table_name} (no file)")
        return

    rows: list[dict[str, object]] = json.loads(file_path.read_text())  # pyright: ignore[reportAny]
    if not rows:
        print(f"  Skipping {table_name} (empty)")
        return

    sa_table = Base.metadata.tables[table_name]
    datetime_cols = get_datetime_columns(sa_table)
    if datetime_cols:
        rows = [parse_datetime_columns(row, datetime_cols) for row in rows]

    # Self-referential tables have unique constraints that prevent bulk insert with NULLs.
    # Insert one row at a time in ID order so each row's self-reference already exists.
    if table_name in SELF_REFERENTIAL_TABLES:
        sorted_rows = sorted(rows, key=lambda r: cast(int, r["id"]))
        for row in sorted_rows:
            _ = await conn.execute(sa_table.insert(), [row])
    else:
        _ = await conn.execute(sa_table.insert(), rows)
    print(f"  Inserted {len(rows)} rows into {table_name}")


async def import_fixtures(fixture_dir: Path) -> None:
    engine = create_async_engine(SETTINGS.DATABASE_URL.render_as_string(hide_password=False))

    async with engine.begin() as conn:
        for table_name in TABLE_ORDER:
            await import_table(conn, table_name, fixture_dir)

        # Reset sequences so new rows get correct auto-increment IDs.
        # Advanced Alchemy uses standalone Sequence objects named {table}_id_seq
        # (not column-owned serials), so pg_get_serial_sequence won't find them.
        for table_name in TABLE_ORDER:
            if table_name in Base.metadata.tables:
                seq_name = f"{table_name}_id_seq"
                _ = await conn.execute(
                    text(f"""SELECT setval('{seq_name}', COALESCE((SELECT MAX(id) FROM "{table_name}"), 1))""")
                )
        print("  Sequences reset")

    await engine.dispose()
    print("Done!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import JSON fixture files into the database.")
    _ = parser.add_argument(
        "fixture_dir",
        type=Path,
        nargs="?",
        default=Path("fixtures/local_db_backup"),
        help="Directory containing JSON fixture files (default: fixtures/local_db_backup)",
    )
    args = parser.parse_args()
    fixture_dir = cast(Path, args.fixture_dir)

    print(f"Importing fixtures from {fixture_dir}")
    asyncio.run(import_fixtures(fixture_dir))
