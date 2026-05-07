"""Tests for slug-or-sqid path resolution helpers."""

from __future__ import annotations

import datetime as dt
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from convergence_games.app.exceptions import SlugRedirectError
from convergence_games.app.routers.frontend.common import _decode_sqid_safely, looks_like_sqid
from convergence_games.app.routers.frontend.game import (
    _resolve_event_for_game,
    _resolve_game_for_event,
)
from convergence_games.db.models import Base, Event, Game, System, User
from convergence_games.db.ocean import swim


@pytest_asyncio.fixture
async def session() -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


# --- looks_like_sqid heuristic ---


def test_looks_like_sqid_uppercase_value() -> None:
    assert looks_like_sqid("Xy7aB") is True


def test_looks_like_sqid_lowercase_alnum() -> None:
    """Ambiguous case — return True so caller falls back to sqid decode."""
    assert looks_like_sqid("abc123") is True


def test_looks_like_sqid_kebab_case() -> None:
    assert looks_like_sqid("convergence-2026") is False


def test_looks_like_sqid_empty() -> None:
    assert looks_like_sqid("") is False


# --- _decode_sqid_safely ---


def test_decode_sqid_safely_valid() -> None:
    sqid = swim("Event", 42)
    assert _decode_sqid_safely(sqid) == 42


def test_decode_sqid_safely_invalid_returns_none() -> None:
    # Lowercase letters not in the default alphabet may decode to nothing.
    assert _decode_sqid_safely("convergence-2026") is None
    assert _decode_sqid_safely("notavalidsqid!@#") is None


# --- _resolve_event_for_game ---


@pytest_asyncio.fixture
async def seeded_event(session: AsyncSession) -> Event:
    now = dt.datetime.now(dt.UTC)
    event = Event(name="Convergence 2026", slug="convergence-2026", start_date=now, end_date=now)
    session.add(event)
    await session.flush()
    return event


@pytest.mark.asyncio
async def test_resolve_event_by_slug(session: AsyncSession, seeded_event: Event) -> None:
    event, via_sqid = await _resolve_event_for_game(session, "convergence-2026")
    assert event.id == seeded_event.id
    assert via_sqid is False


@pytest.mark.asyncio
async def test_resolve_event_by_sqid_marks_redirect(session: AsyncSession, seeded_event: Event) -> None:
    sqid = swim(seeded_event)
    event, via_sqid = await _resolve_event_for_game(session, sqid)
    assert event.id == seeded_event.id
    assert via_sqid is True


@pytest.mark.asyncio
async def test_resolve_event_unknown_slug_404(session: AsyncSession, seeded_event: Event) -> None:
    from litestar.exceptions import HTTPException

    with pytest.raises(HTTPException) as excinfo:
        await _resolve_event_for_game(session, "no-such-event")
    assert excinfo.value.status_code == 404


# --- _resolve_game_for_event ---


@pytest_asyncio.fixture
async def seeded_game(session: AsyncSession, seeded_event: Event) -> Game:
    system = System(name="Test System")
    user = User(first_name="GM", last_name="Person")
    session.add_all([system, user])
    await session.flush()
    game = Game(
        name="Dragons of Doom",
        slug="dragons-of-doom",
        event_id=seeded_event.id,
        system_id=system.id,
        gamemaster_id=user.id,
        player_count_minimum=1,
        player_count_optimum=3,
        player_count_maximum=5,
    )
    session.add(game)
    await session.flush()
    return game


@pytest.mark.asyncio
async def test_resolve_game_by_slug(session: AsyncSession, seeded_event: Event, seeded_game: Game) -> None:
    game, via_sqid = await _resolve_game_for_event(session, seeded_event, "dragons-of-doom")
    assert game.id == seeded_game.id
    assert via_sqid is False


@pytest.mark.asyncio
async def test_resolve_game_by_sqid_marks_redirect(
    session: AsyncSession, seeded_event: Event, seeded_game: Game
) -> None:
    sqid = swim(seeded_game)
    game, via_sqid = await _resolve_game_for_event(session, seeded_event, sqid)
    assert game.id == seeded_game.id
    assert via_sqid is True


@pytest.mark.asyncio
async def test_resolve_game_unknown_404(session: AsyncSession, seeded_event: Event) -> None:
    from litestar.exceptions import HTTPException

    with pytest.raises(HTTPException) as excinfo:
        await _resolve_game_for_event(session, seeded_event, "no-such-game")
    assert excinfo.value.status_code == 404


# --- SlugRedirectError ---


def test_slug_redirect_error_carries_path() -> None:
    exc = SlugRedirectError("/event/convergence-2026/games")
    assert exc.path == "/event/convergence-2026/games"
    assert str(exc) == "/event/convergence-2026/games"
