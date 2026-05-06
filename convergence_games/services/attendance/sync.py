"""Attendance sync service.

Single entry point: ``sync_attendance_for_timeslot``. Called from the
allocation-commit handler in ``put_event_manage_allocation`` and intended to
be the only writer of ``SessionAttendance`` in normal operation.

Idempotent: re-running with the same committed allocations leaves the
attendance rows unchanged. Re-running after a player is removed from a
party deletes that user's row. Re-running after a session swaps games
updates the existing row's ``game_id`` rather than churning the row.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from convergence_games.db.enums import AttendanceRole, AttendanceSource
from convergence_games.db.models import (
    Allocation,
    Game,
    Party,
    PartyUserLink,
    Session,
    SessionAttendance,
)


@dataclass(frozen=True)
class AllocationRow:
    """One committed Allocation joined to its Session and Game."""

    allocation_id: int
    party_leader_id: int
    game_id: int
    table_id: int | None
    gamemaster_id: int


@dataclass(frozen=True)
class PartyMemberRow:
    """One row of (party_id, user_id, is_leader) for a timeslot."""

    party_id: int
    user_id: int
    is_leader: bool


@dataclass(frozen=True)
class DesiredAttendance:
    game_id: int
    role: AttendanceRole
    table_id: int | None
    source_allocation_id: int


def compute_desired_attendance(
    allocation_rows: Iterable[AllocationRow],
    party_member_rows: Iterable[PartyMemberRow],
) -> dict[int, DesiredAttendance]:
    """Pure transformation of raw rows into the desired ``user_id -> attendance`` map.

    Extracted from ``sync_attendance_for_timeslot`` so it can be unit-tested
    without a live database connection.
    """
    party_to_members: dict[int, list[int]] = {}
    party_to_leader: dict[int, int] = {}
    for row in party_member_rows:
        party_to_members.setdefault(row.party_id, []).append(row.user_id)
        if row.is_leader:
            party_to_leader[row.party_id] = row.user_id
    leader_to_members: dict[int, list[int]] = {
        leader_id: party_to_members[party_id] for party_id, leader_id in party_to_leader.items()
    }

    desired: dict[int, DesiredAttendance] = {}
    for row in allocation_rows:
        if row.party_leader_id == row.gamemaster_id:
            desired[row.party_leader_id] = DesiredAttendance(
                game_id=row.game_id,
                role=AttendanceRole.GAMEMASTER,
                table_id=row.table_id,
                source_allocation_id=row.allocation_id,
            )
        else:
            members = leader_to_members.get(row.party_leader_id, [row.party_leader_id])
            for member_id in members:
                _ = desired.setdefault(
                    member_id,
                    DesiredAttendance(
                        game_id=row.game_id,
                        role=AttendanceRole.PLAYER,
                        table_id=row.table_id,
                        source_allocation_id=row.allocation_id,
                    ),
                )
    return desired


async def sync_attendance_for_timeslot(
    transaction: AsyncSession,
    *,
    time_slot_id: int,
    event_id: int,
    source: AttendanceSource = AttendanceSource.COMMIT,
) -> None:
    """Rewrite ``SessionAttendance`` rows for a single timeslot.

    Reads every committed Allocation for the timeslot, expands each
    party leader's party to all members, and produces one attendance row
    per (user, slot) -- role ``GAMEMASTER`` when the leader is the game's
    gamemaster (party-of-one GM rows), else ``PLAYER`` for every party
    member.

    Existing rows are upserted via ``INSERT ... ON CONFLICT (event_id,
    time_slot_id, user_id) DO UPDATE``. Rows for users no longer in any
    committed allocation for the slot are deleted.
    """
    allocations_stmt = (
        select(
            Allocation.id.label("allocation_id"),
            Allocation.party_leader_id,
            Session.game_id,
            Session.table_id,
            Game.gamemaster_id,
        )
        .join(Session, Allocation.session_id == Session.id)
        .join(Game, Session.game_id == Game.id)
        .where(Session.time_slot_id == time_slot_id)
        .where(Allocation.committed.is_(True))
    )
    allocation_rows = [
        AllocationRow(
            allocation_id=r.allocation_id,
            party_leader_id=r.party_leader_id,
            game_id=r.game_id,
            table_id=r.table_id,
            gamemaster_id=r.gamemaster_id,
        )
        for r in (await transaction.execute(allocations_stmt)).all()
    ]

    party_member_rows = [
        PartyMemberRow(party_id=r[0], user_id=r[1], is_leader=r[2])
        for r in (
            await transaction.execute(
                select(Party.id, PartyUserLink.user_id, PartyUserLink.is_leader)
                .join(PartyUserLink, PartyUserLink.party_id == Party.id)
                .where(Party.time_slot_id == time_slot_id)
            )
        ).all()
    ]

    desired = compute_desired_attendance(allocation_rows, party_member_rows)

    if desired:
        values = [
            {
                "event_id": event_id,
                "time_slot_id": time_slot_id,
                "user_id": user_id,
                "game_id": attendance.game_id,
                "role": attendance.role,
                "table_id": attendance.table_id,
                "source_allocation_id": attendance.source_allocation_id,
                "source": source,
            }
            for user_id, attendance in desired.items()
        ]
        upsert_stmt = pg_insert(SessionAttendance).values(values)
        upsert_stmt = upsert_stmt.on_conflict_do_update(
            index_elements=["event_id", "time_slot_id", "user_id"],
            set_={
                "game_id": upsert_stmt.excluded.game_id,
                "role": upsert_stmt.excluded.role,
                "table_id": upsert_stmt.excluded.table_id,
                "source_allocation_id": upsert_stmt.excluded.source_allocation_id,
                "source": upsert_stmt.excluded.source,
                "updated_at": func.now(),
            },
        )
        _ = await transaction.execute(upsert_stmt)

    delete_stmt = delete(SessionAttendance).where(
        SessionAttendance.event_id == event_id,
        SessionAttendance.time_slot_id == time_slot_id,
    )
    if desired:
        delete_stmt = delete_stmt.where(SessionAttendance.user_id.notin_(desired.keys()))
    _ = await transaction.execute(delete_stmt)
