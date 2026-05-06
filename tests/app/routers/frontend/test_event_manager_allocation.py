"""Tests for the diff-based allocation save in ``put_event_manage_allocation``.

Regression tests for the secondary data-loss bug where saving an allocation
draft unconditionally deleted every Allocation row for the timeslot,
including committed ones. After the fix, draft saves only diff against
uncommitted rows; committed rows survive untouched.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from convergence_games.app.routers.frontend import event_manager as event_manager_module
from convergence_games.app.routers.frontend.event_manager import (
    EventManagerController,
    PutEventManageAllocationForm,
    PutEventManageAllocationSession,
)
from convergence_games.db.models import (
    Allocation,
    Base,
    Event,
    Game,
    GameRequirement,
    Room,
    Session,
    System,
    Table,
    TimeSlot,
    User,
)
from convergence_games.db.ocean import swim


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def _build_event(s: AsyncSession) -> tuple[Event, TimeSlot, Table, Game, User]:
    """Build an Event with one timeslot, one table, one game, and one player."""
    gm = User(first_name="GM", last_name="One")
    player = User(first_name="Player", last_name="One")
    system = System(name="Test RPG")
    now = dt.datetime.now(dt.UTC)
    event = Event(name="Test Event", description="", start_date=now, end_date=now + dt.timedelta(days=1))
    s.add_all([gm, player, system, event])
    await s.flush()

    room = Room(name="Hall", event_id=event.id)
    s.add(room)
    await s.flush()

    table = Table(name="T1", room_id=room.id, event_id=event.id)
    time_slot = TimeSlot(name="Slot 1", start_time=now, end_time=now + dt.timedelta(hours=4), event_id=event.id)
    s.add_all([table, time_slot])
    await s.flush()

    game = Game(
        name="The Game",
        player_count_minimum=2,
        player_count_optimum=4,
        player_count_maximum=6,
        system_id=system.id,
        gamemaster_id=gm.id,
        event_id=event.id,
    )
    s.add(game)
    await s.flush()
    s.add(GameRequirement(game_id=game.id, event_id=event.id))
    await s.flush()

    return event, time_slot, table, game, player


async def _reload_event_with_timeslots(s: AsyncSession, event_id: int) -> Event:
    return (
        await s.execute(select(Event).where(Event.id == event_id).options(selectinload(Event.time_slots)))
    ).scalar_one()


async def test_uncommitted_draft_save_preserves_committed_allocations(
    db_session: AsyncSession,
    monkeypatch,  # type: ignore[no-untyped-def]
) -> None:
    # No commits in this test path, so no need to patch sync_attendance_for_timeslot.
    event, time_slot, table, game, player = await _build_event(db_session)

    s_row = Session(
        event_id=event.id,
        time_slot_id=time_slot.id,
        table_id=table.id,
        game_id=game.id,
        committed=False,
    )
    s_row_committed = Session(
        event_id=event.id,
        time_slot_id=time_slot.id,
        table_id=table.id,
        game_id=game.id,
        committed=True,
    )
    db_session.add_all([s_row, s_row_committed])
    await db_session.flush()

    committed_alloc = Allocation(party_leader_id=player.id, session_id=s_row_committed.id, committed=True)
    db_session.add(committed_alloc)
    await db_session.flush()
    committed_alloc_id = committed_alloc.id

    event = await _reload_event_with_timeslots(db_session, event.id)
    controller = EventManagerController(owner=None)

    # Save an empty uncommitted draft. Committed allocation should survive.
    _ = await controller.put_event_manage_allocation.fn(
        controller,
        request=None,  # type: ignore[arg-type]
        transaction=db_session,
        permission=True,
        event=event,
        time_slot_sqid=swim(time_slot),
        data=PutEventManageAllocationForm.model_construct(allocations=[], commit=False),
    )
    await db_session.flush()

    rows = (
        (await db_session.execute(select(Allocation).where(Allocation.session_id.in_([s_row.id, s_row_committed.id]))))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].id == committed_alloc_id
    assert rows[0].committed is True


async def test_commit_triggers_attendance_sync(db_session: AsyncSession, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The commit path must call sync_attendance_for_timeslot.

    The real sync uses Postgres-only ``ON CONFLICT``; under sqlite we patch
    it out and assert the call site invokes it.
    """
    event, time_slot, table, game, player = await _build_event(db_session)

    s_row = Session(
        event_id=event.id,
        time_slot_id=time_slot.id,
        table_id=table.id,
        game_id=game.id,
        committed=False,
    )
    db_session.add(s_row)
    await db_session.flush()

    fake_sync = AsyncMock(return_value=None)
    monkeypatch.setattr(event_manager_module, "sync_attendance_for_timeslot", fake_sync)

    event = await _reload_event_with_timeslots(db_session, event.id)
    controller = EventManagerController(owner=None)

    _ = await controller.put_event_manage_allocation.fn(
        controller,
        request=None,  # type: ignore[arg-type]
        transaction=db_session,
        permission=True,
        event=event,
        time_slot_sqid=swim(time_slot),
        data=PutEventManageAllocationForm.model_construct(
            allocations=[
                PutEventManageAllocationSession.model_construct(leader=player.id, session=s_row.id),
            ],
            commit=True,
        ),
    )

    fake_sync.assert_awaited_once()
    call_kwargs = fake_sync.await_args.kwargs
    assert call_kwargs["time_slot_id"] == time_slot.id
    assert call_kwargs["event_id"] == event.id


async def test_draft_save_does_not_trigger_attendance_sync(
    db_session: AsyncSession,
    monkeypatch,  # type: ignore[no-untyped-def]
) -> None:
    event, time_slot, table, game, player = await _build_event(db_session)

    s_row = Session(
        event_id=event.id,
        time_slot_id=time_slot.id,
        table_id=table.id,
        game_id=game.id,
        committed=False,
    )
    db_session.add(s_row)
    await db_session.flush()

    fake_sync = AsyncMock(return_value=None)
    monkeypatch.setattr(event_manager_module, "sync_attendance_for_timeslot", fake_sync)

    event = await _reload_event_with_timeslots(db_session, event.id)
    controller = EventManagerController(owner=None)

    _ = await controller.put_event_manage_allocation.fn(
        controller,
        request=None,  # type: ignore[arg-type]
        transaction=db_session,
        permission=True,
        event=event,
        time_slot_sqid=swim(time_slot),
        data=PutEventManageAllocationForm.model_construct(
            allocations=[
                PutEventManageAllocationSession.model_construct(leader=player.id, session=s_row.id),
            ],
            commit=False,
        ),
    )

    fake_sync.assert_not_called()
