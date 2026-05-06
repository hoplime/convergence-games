"""Tests for the diff-based schedule save in ``put_event_manage_schedule``.

Regression tests for the data-loss bug where saving the schedule
deleted every Session row in the event (and cascaded through to delete
every Allocation). After the fix, identical saves preserve session
primary keys; only added/removed sessions cause INSERTs/DELETEs.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import AsyncGenerator

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from convergence_games.app.routers.frontend.event_manager import (
    EventManagerController,
    PutEventManageScheduleForm,
    PutEventManageScheduleSession,
)
from convergence_games.db.models import (
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


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def _build_minimal_event(s: AsyncSession) -> tuple[Event, list[TimeSlot], list[Table], list[Game]]:
    """Build an Event with 2 timeslots, 2 tables, and 3 games."""
    user = User(first_name="GM", last_name="One")
    system = System(name="Test RPG")
    now = dt.datetime.now(dt.UTC)
    event = Event(name="Test Event", description="", start_date=now, end_date=now + dt.timedelta(days=1))
    s.add_all([user, system, event])
    await s.flush()

    room = Room(name="Main Hall", event_id=event.id)
    s.add(room)
    await s.flush()

    tables = [
        Table(name="Table A", room_id=room.id, event_id=event.id),
        Table(name="Table B", room_id=room.id, event_id=event.id),
    ]
    s.add_all(tables)

    time_slots = [
        TimeSlot(name="Slot 1", start_time=now, end_time=now + dt.timedelta(hours=4), event_id=event.id),
        TimeSlot(
            name="Slot 2",
            start_time=now + dt.timedelta(hours=5),
            end_time=now + dt.timedelta(hours=9),
            event_id=event.id,
        ),
    ]
    s.add_all(time_slots)
    await s.flush()

    games: list[Game] = []
    for i in range(3):
        g = Game(
            name=f"Game {i + 1}",
            player_count_minimum=2,
            player_count_optimum=4,
            player_count_maximum=6,
            system_id=system.id,
            gamemaster_id=user.id,
            event_id=event.id,
        )
        s.add(g)
        await s.flush()
        s.add(GameRequirement(game_id=g.id, event_id=event.id))
        games.append(g)
    await s.flush()

    return event, time_slots, tables, games


async def _reload_event_with_sessions(s: AsyncSession, event_id: int) -> Event:
    event = (
        await s.execute(select(Event).where(Event.id == event_id).options(selectinload(Event.sessions)))
    ).scalar_one()
    return event


async def test_identical_save_preserves_session_ids(db_session: AsyncSession) -> None:
    event, time_slots, tables, games = await _build_minimal_event(db_session)

    initial = Session(
        event_id=event.id,
        time_slot_id=time_slots[0].id,
        table_id=tables[0].id,
        game_id=games[0].id,
        committed=False,
    )
    db_session.add(initial)
    await db_session.flush()
    initial_id = initial.id

    event = await _reload_event_with_sessions(db_session, event.id)
    controller = EventManagerController(owner=None)

    _ = await controller.put_event_manage_schedule.fn(
        controller,
        event=event,
        permission=True,
        transaction=db_session,
        data=PutEventManageScheduleForm.model_construct(
            sessions=[
                PutEventManageScheduleSession.model_construct(
                    game=games[0].id, table=tables[0].id, time_slot=time_slots[0].id
                ),
            ],
            commit=False,
        ),
    )
    await db_session.flush()

    rows = (await db_session.execute(select(Session).where(Session.event_id == event.id))).scalars().all()
    assert len(rows) == 1
    assert rows[0].id == initial_id


async def test_moving_one_session_preserves_others(db_session: AsyncSession) -> None:
    event, time_slots, tables, games = await _build_minimal_event(db_session)

    a = Session(
        event_id=event.id,
        time_slot_id=time_slots[0].id,
        table_id=tables[0].id,
        game_id=games[0].id,
        committed=False,
    )
    b = Session(
        event_id=event.id,
        time_slot_id=time_slots[0].id,
        table_id=tables[1].id,
        game_id=games[1].id,
        committed=False,
    )
    db_session.add_all([a, b])
    await db_session.flush()
    keep_id = a.id

    event = await _reload_event_with_sessions(db_session, event.id)
    controller = EventManagerController(owner=None)

    # Re-save with session A unchanged but session B replaced (different game on the same table+slot).
    _ = await controller.put_event_manage_schedule.fn(
        controller,
        event=event,
        permission=True,
        transaction=db_session,
        data=PutEventManageScheduleForm.model_construct(
            sessions=[
                PutEventManageScheduleSession.model_construct(
                    game=games[0].id, table=tables[0].id, time_slot=time_slots[0].id
                ),
                PutEventManageScheduleSession.model_construct(
                    game=games[2].id, table=tables[1].id, time_slot=time_slots[0].id
                ),
            ],
            commit=False,
        ),
    )
    await db_session.flush()

    rows = (await db_session.execute(select(Session).where(Session.event_id == event.id))).scalars().all()
    assert len(rows) == 2
    ids = {r.id for r in rows}
    assert keep_id in ids


async def test_committed_sessions_untouched_by_draft_save(db_session: AsyncSession) -> None:
    event, time_slots, tables, games = await _build_minimal_event(db_session)

    committed = Session(
        event_id=event.id,
        time_slot_id=time_slots[0].id,
        table_id=tables[0].id,
        game_id=games[0].id,
        committed=True,
    )
    uncommitted = Session(
        event_id=event.id,
        time_slot_id=time_slots[0].id,
        table_id=tables[1].id,
        game_id=games[1].id,
        committed=False,
    )
    db_session.add_all([committed, uncommitted])
    await db_session.flush()
    committed_id = committed.id

    event = await _reload_event_with_sessions(db_session, event.id)
    controller = EventManagerController(owner=None)

    # Draft save with a different uncommitted set; committed row should be untouched.
    _ = await controller.put_event_manage_schedule.fn(
        controller,
        event=event,
        permission=True,
        transaction=db_session,
        data=PutEventManageScheduleForm.model_construct(
            sessions=[
                PutEventManageScheduleSession.model_construct(
                    game=games[2].id, table=tables[0].id, time_slot=time_slots[1].id
                ),
            ],
            commit=False,
        ),
    )
    await db_session.flush()

    committed_rows = (
        (await db_session.execute(select(Session).where(Session.event_id == event.id, Session.committed.is_(True))))
        .scalars()
        .all()
    )
    assert len(committed_rows) == 1
    assert committed_rows[0].id == committed_id


async def test_removed_session_is_deleted(db_session: AsyncSession) -> None:
    event, time_slots, tables, games = await _build_minimal_event(db_session)

    a = Session(
        event_id=event.id,
        time_slot_id=time_slots[0].id,
        table_id=tables[0].id,
        game_id=games[0].id,
        committed=False,
    )
    b = Session(
        event_id=event.id,
        time_slot_id=time_slots[0].id,
        table_id=tables[1].id,
        game_id=games[1].id,
        committed=False,
    )
    db_session.add_all([a, b])
    await db_session.flush()

    event = await _reload_event_with_sessions(db_session, event.id)
    controller = EventManagerController(owner=None)

    # Save with only session A; B should be deleted.
    _ = await controller.put_event_manage_schedule.fn(
        controller,
        event=event,
        permission=True,
        transaction=db_session,
        data=PutEventManageScheduleForm.model_construct(
            sessions=[
                PutEventManageScheduleSession.model_construct(
                    game=games[0].id, table=tables[0].id, time_slot=time_slots[0].id
                ),
            ],
            commit=False,
        ),
    )
    await db_session.flush()

    rows = (await db_session.execute(select(Session).where(Session.event_id == event.id))).scalars().all()
    assert len(rows) == 1
    assert rows[0].id == a.id
