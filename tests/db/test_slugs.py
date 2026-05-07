"""Tests for slug generation and regeneration."""

from __future__ import annotations

import datetime as dt
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from convergence_games.db.models import Base, Event, Game, System, User
from convergence_games.db.slugs import (
    generate_unique_slug,
    maybe_regenerate_slug,
    slugify,
)


@pytest_asyncio.fixture
async def session() -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def _make_event(session: AsyncSession, name: str, *, slug: str | None = None) -> Event:
    now = dt.datetime.now(dt.UTC)
    event = Event(name=name, start_date=now, end_date=now)
    if slug is not None:
        event.slug = slug
    session.add(event)
    await session.flush()
    return event


async def _make_system(session: AsyncSession, name: str = "Test System") -> System:
    system = System(name=name)
    session.add(system)
    await session.flush()
    return system


async def _make_user(session: AsyncSession, first_name: str = "", last_name: str = "") -> User:
    user = User(first_name=first_name, last_name=last_name)
    session.add(user)
    await session.flush()
    return user


async def _make_game(
    session: AsyncSession,
    *,
    name: str,
    event: Event,
    system: System,
    gamemaster: User,
    slug: str | None = None,
) -> Game:
    game = Game(
        name=name,
        event_id=event.id,
        system_id=system.id,
        gamemaster_id=gamemaster.id,
        player_count_minimum=1,
        player_count_optimum=3,
        player_count_maximum=5,
    )
    if slug is not None:
        game.slug = slug
    session.add(game)
    await session.flush()
    return game


# --- slugify ---


def test_slugify_basic() -> None:
    assert slugify("Convergence 2026") == "convergence-2026"


def test_slugify_strips_punctuation() -> None:
    assert slugify("Foo? Bar!") == "foo-bar"


def test_slugify_empty_for_punctuation_only() -> None:
    assert slugify("???") == ""


# --- generate_unique_slug ---


@pytest.mark.asyncio
async def test_generate_unique_slug_first_use(session: AsyncSession) -> None:
    slug = await generate_unique_slug(session, Event, "Convergence 2026")
    assert slug == "convergence-2026"


@pytest.mark.asyncio
async def test_generate_unique_slug_collision_appends_suffix(session: AsyncSession) -> None:
    await _make_event(session, "Convergence 2026", slug="convergence-2026")
    slug = await generate_unique_slug(session, Event, "Convergence 2026")
    assert slug != "convergence-2026"
    assert slug.startswith("convergence-2026-")
    assert len(slug) == len("convergence-2026") + 5  # base + "-xxxx"


@pytest.mark.asyncio
async def test_generate_unique_slug_fallback_for_empty(session: AsyncSession) -> None:
    slug = await generate_unique_slug(session, Event, "???", fallback="event")
    assert slug == "event"


@pytest.mark.asyncio
async def test_generate_unique_slug_scoped_per_event(session: AsyncSession) -> None:
    """Game slugs are unique per event_id, not table-wide."""
    event_a = await _make_event(session, "Event A", slug="event-a")
    event_b = await _make_event(session, "Event B", slug="event-b")
    system = await _make_system(session)
    gm = await _make_user(session, first_name="Alice", last_name="Smith")

    slug_a = await generate_unique_slug(session, Game, "Dragons of Doom", scope={"event_id": event_a.id})
    await _make_game(session, name="Dragons of Doom", event=event_a, system=system, gamemaster=gm, slug=slug_a)

    # Same name in a different event — should get the bare slug, no suffix.
    slug_b = await generate_unique_slug(session, Game, "Dragons of Doom", scope={"event_id": event_b.id})
    assert slug_a == "dragons-of-doom"
    assert slug_b == "dragons-of-doom"


@pytest.mark.asyncio
async def test_generate_unique_slug_scoped_collision(session: AsyncSession) -> None:
    """Two games with the same name in the same event collide; second gets suffix."""
    event = await _make_event(session, "Event A", slug="event-a")
    system = await _make_system(session)
    gm = await _make_user(session, first_name="Alice", last_name="Smith")

    slug1 = await generate_unique_slug(session, Game, "Dragons of Doom", scope={"event_id": event.id})
    await _make_game(session, name="Dragons of Doom", event=event, system=system, gamemaster=gm, slug=slug1)

    slug2 = await generate_unique_slug(session, Game, "Dragons of Doom", scope={"event_id": event.id})
    assert slug1 == "dragons-of-doom"
    assert slug2.startswith("dragons-of-doom-")
    assert slug2 != slug1


@pytest.mark.asyncio
async def test_generate_unique_slug_excludes_self(session: AsyncSession) -> None:
    """exclude_id ignores the entity's own current slug."""
    event = await _make_event(session, "Event A", slug="event-a")
    # No conflict because we exclude this row.
    slug = await generate_unique_slug(session, Event, "Event A", exclude_id=event.id)
    assert slug == "event-a"


# --- maybe_regenerate_slug ---


@pytest.mark.asyncio
async def test_maybe_regenerate_slug_noop_when_aligned(session: AsyncSession) -> None:
    event = await _make_event(session, "Event A", slug="event-a")
    original = event.slug
    await maybe_regenerate_slug(session, event, source=event.name)
    assert event.slug == original


@pytest.mark.asyncio
async def test_maybe_regenerate_slug_noop_when_aligned_with_suffix(session: AsyncSession) -> None:
    """Slug `event-a-xy7q` should stay put when source is still 'Event A'."""
    event = await _make_event(session, "Event A", slug="event-a-xy7q")
    await maybe_regenerate_slug(session, event, source="Event A")
    assert event.slug == "event-a-xy7q"


@pytest.mark.asyncio
async def test_maybe_regenerate_slug_rerolls_on_rename(session: AsyncSession) -> None:
    event = await _make_event(session, "Original Name", slug="original-name")
    event.name = "New Name"
    await maybe_regenerate_slug(session, event, source=event.name)
    assert event.slug == "new-name"


@pytest.mark.asyncio
async def test_maybe_regenerate_slug_collision_against_others(session: AsyncSession) -> None:
    """A rename that collides with another row gets a -xxxx suffix; the row's own current slug doesn't count."""
    # `Event.name` itself is unique, so we can't actually rename to a duplicate name.
    # Use Game (no name uniqueness) and the Game scope to test slug-only collision.
    event = await _make_event(session, "Event A", slug="event-a")
    system = await _make_system(session)
    gm = await _make_user(session, first_name="Alice", last_name="Smith")
    other = await _make_game(
        session, name="Already Taken", event=event, system=system, gamemaster=gm, slug="already-taken"
    )
    game = await _make_game(session, name="Source Game", event=event, system=system, gamemaster=gm, slug="source-game")

    game.name = "Already Taken"
    await maybe_regenerate_slug(session, game, source=game.name, scope={"event_id": event.id})
    assert game.slug != other.slug
    assert game.slug.startswith("already-taken-")


@pytest.mark.asyncio
async def test_user_placeholder_via_listener(session: AsyncSession) -> None:
    """A User flushed without an explicit slug gets a `user-<random>` placeholder."""
    user = await _make_user(session)
    assert user.slug
    assert user.slug.startswith("user-")
