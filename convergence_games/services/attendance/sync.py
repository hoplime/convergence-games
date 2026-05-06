"""Attendance sync service.

Single entry point: ``sync_attendance_for_timeslot``. Called from the
allocation-commit handler in ``put_event_manage_allocation`` and intended to
be the only writer of ``SessionAttendance`` in normal operation.

Idempotent: re-running with the same committed allocations leaves the
attendance rows unchanged. Re-running after a player is removed from a
party deletes that user's row. Re-running after a session swaps games
updates the existing row's ``game_id`` rather than churning the row.
"""

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
    allocation_rows = (await transaction.execute(allocations_stmt)).all()

    party_member_rows = (
        await transaction.execute(
            select(Party.id, PartyUserLink.user_id, PartyUserLink.is_leader)
            .join(PartyUserLink, PartyUserLink.party_id == Party.id)
            .where(Party.time_slot_id == time_slot_id)
        )
    ).all()

    # Map party_id -> list of member user_ids, and party_id -> leader user_id.
    party_to_members: dict[int, list[int]] = {}
    party_to_leader: dict[int, int] = {}
    for party_id, user_id, is_leader in party_member_rows:
        party_to_members.setdefault(party_id, []).append(user_id)
        if is_leader:
            party_to_leader[party_id] = user_id
    leader_to_members: dict[int, list[int]] = {
        leader_id: party_to_members[party_id] for party_id, leader_id in party_to_leader.items()
    }

    # Build desired set: user_id -> (game_id, role, table_id, source_allocation_id).
    # GM rows take precedence (in the unlikely event a user is both GM and
    # party member in the same slot, the unique constraint will surface it
    # via IntegrityError).
    desired: dict[int, tuple[int, AttendanceRole, int | None, int]] = {}
    for row in allocation_rows:
        if row.party_leader_id == row.gamemaster_id:
            desired[row.party_leader_id] = (
                row.game_id,
                AttendanceRole.GAMEMASTER,
                row.table_id,
                row.allocation_id,
            )
        else:
            members = leader_to_members.get(row.party_leader_id, [row.party_leader_id])
            for member_id in members:
                _ = desired.setdefault(
                    member_id,
                    (row.game_id, AttendanceRole.PLAYER, row.table_id, row.allocation_id),
                )

    if desired:
        values = [
            {
                "event_id": event_id,
                "time_slot_id": time_slot_id,
                "user_id": user_id,
                "game_id": game_id,
                "role": role,
                "table_id": table_id,
                "source_allocation_id": source_allocation_id,
                "source": source,
            }
            for user_id, (game_id, role, table_id, source_allocation_id) in desired.items()
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
