from __future__ import annotations

import itertools
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated, Literal

import humanize
from litestar import Controller, Response, get, put
from litestar.di import Provide
from litestar.exceptions import HTTPException
from litestar.params import Body, Parameter, RequestEncodingType
from litestar.status_codes import HTTP_200_OK, HTTP_204_NO_CONTENT
from pydantic import BaseModel, BeforeValidator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.base import ExecutableOption

from convergence_games.app.guards import permission_check, user_guard
from convergence_games.app.request_type import Request
from convergence_games.app.response_type import HTMXBlockTemplate, Template
from convergence_games.db.enums import GameKSP, GameTone, SubmissionStatus, UserGamePreferenceValue
from convergence_games.db.models import (
    ContentWarning,
    Event,
    Game,
    GameContentWarningLink,
    GameGenreLink,
    GameRequirement,
    Genre,
    Room,
    Session,
    System,
    User,
    UserGamePreference,
)
from convergence_games.db.ocean import Sqid, sink, swim
from convergence_games.permissions import user_has_permission


def event_with(*options: ExecutableOption):
    async def wrapper(
        transaction: AsyncSession,
        event_sqid: Sqid | None = None,
    ) -> Event:
        event_id: int = sink(event_sqid) if event_sqid is not None else 1
        stmt = select(Event).options(*options).where(Event.id == event_id)
        event = (await transaction.execute(stmt)).scalar_one_or_none()
        if event is None:
            raise HTTPException(status_code=404, detail="Event not found")
        return event

    return Provide(wrapper)


async def get_event_games_dep(
    event: Event,  # This forces the dependencies to be in a chain, meaning the transaction isn't closed yet
    transaction: AsyncSession,
    sort: Literal["title", "system", "gamemaster", "submitted", "status", "sessions"] = "submitted",
    desc: bool = False,
) -> Sequence[Game]:
    event_id: int = event.id

    # TODO: Technical typing TODO - an eliminator or TypeIs check for the sort
    query_order_by = {
        "title": Game.name,
        "submitted": Game.created_at,
        "status": Game.submission_status,
    }.get(sort)
    if query_order_by is not None and desc:
        query_order_by = query_order_by.desc()  # type: ignore

    stmt = (
        select(Game)
        .options(
            selectinload(Game.system),
            selectinload(Game.gamemaster),
            selectinload(Game.game_requirement),
            selectinload(Game.event),
        )
        .order_by(query_order_by)
        .where(Game.event_id == event_id)
    )
    games = (await transaction.execute(stmt)).scalars().all()

    if query_order_by is None:

        def by_system(g: Game) -> str:
            return g.system.name.lower()

        def by_gamemaster(g: Game) -> str:
            return g.gamemaster.last_name.lower()

        def by_sessions(g: Game) -> int:
            return g.game_requirement.times_to_run

        post_order_by = {
            "system": by_system,
            "gamemaster": by_gamemaster,
            "sessions": by_sessions,
        }.get(sort)

        assert post_order_by is not None, "Invalid sort option"

        games = sorted(games, key=post_order_by, reverse=desc)

    return games


SqidInt = Annotated[int, BeforeValidator(sink)]


class EventGamesQuery(BaseModel):
    genre: list[SqidInt] = []
    system: list[SqidInt] = []
    tone: list[str] = []
    bonus: list[int] = []
    content: list[SqidInt] = []


async def get_event_approved_games_dep(
    event: Event,
    transaction: AsyncSession,
    query_params: EventGamesQuery,
) -> Sequence[Game]:
    event_id: int = event.id
    stmt = (
        select(Game)
        .options(
            selectinload(Game.system),
            selectinload(Game.gamemaster),
            selectinload(Game.game_requirement),
            selectinload(Game.genres),
            selectinload(Game.content_warnings),
            selectinload(Game.event),
        )
        .order_by(Game.name)
        .where(
            Game.event_id == event_id,
            Game.submission_status == SubmissionStatus.APPROVED,
        )
    )
    if query_params.genre:
        stmt = stmt.where(Game.genres.any(Genre.id.in_(query_params.genre)))
    if query_params.system:
        stmt = stmt.where(Game.system_id.in_(query_params.system))
    if query_params.tone:
        stmt = stmt.where(Game.tone.in_(query_params.tone))
    if query_params.bonus:
        stmt = stmt.where(Game.ksps.bitwise_and(sum(query_params.bonus)) > 0)
    if query_params.content:
        stmt = stmt.where(~Game.content_warnings.any(ContentWarning.id.in_(query_params.content)))
    games = (await transaction.execute(stmt)).scalars().all()
    return games


async def build_event_games_query(
    genre: list[Sqid] | Sqid | None = None,
    system: list[Sqid] | Sqid | None = None,
    tone: list[str] | str | None = None,
    bonus: list[int] | int | None = None,
    content: list[Sqid] | Sqid | None = None,
) -> EventGamesQuery:
    return EventGamesQuery.model_validate(
        {
            "genre": [] if genre is None else (genre if isinstance(genre, list) else [genre]),
            "system": [] if system is None else (system if isinstance(system, list) else [system]),
            "tone": [] if tone is None else (tone if isinstance(tone, list) else [tone]),
            "bonus": [] if bonus is None else (bonus if isinstance(bonus, list) else [bonus]),
            "content": [] if content is None else (content if isinstance(content, list) else [content]),
        }
    )


async def get_form_data(
    transaction: AsyncSession,
    event: Event,
    query_params: EventGamesQuery,
) -> dict[str, MultiselectFormData]:
    all_present_genres = (
        (
            await transaction.execute(
                select(Genre)
                .join(GameGenreLink, GameGenreLink.genre_id == Genre.id)
                .join(Game, Game.id == GameGenreLink.game_id)
                .where(Game.event_id == event.id)
                .where(Game.submission_status == SubmissionStatus.APPROVED)
                .order_by(Genre.name)
                .distinct()
            )
        )
        .scalars()
        .all()
    )
    all_present_systems = (
        (
            await transaction.execute(
                select(System)
                .join(Game, Game.system_id == System.id)
                .where(Game.event_id == event.id)
                .where(Game.submission_status == SubmissionStatus.APPROVED)
                .order_by(System.name)
                .distinct()
            )
        )
        .scalars()
        .all()
    )
    all_present_content_warnings = (
        (
            await transaction.execute(
                select(ContentWarning)
                .join(GameContentWarningLink, GameContentWarningLink.content_warning_id == ContentWarning.id)
                .join(Game, Game.id == GameContentWarningLink.game_id)
                .where(Game.event_id == event.id)
                .where(Game.submission_status == SubmissionStatus.APPROVED)
                .order_by(ContentWarning.name)
                .distinct()
            )
        )
        .scalars()
        .all()
    )
    all_tones = list(GameTone)
    all_bonus = list(GameKSP)

    return {
        "genre": MultiselectFormData(
            label="Genre",
            name="genre",
            options=[
                MultiselectFormDataOption(label=genre.name, value=swim(genre), selected=genre.id in query_params.genre)
                for genre in all_present_genres
            ],
            description="Find games tagged with any of these genres:",
        ),
        "system": MultiselectFormData(
            label="System",
            name="system",
            options=[
                MultiselectFormDataOption(
                    label=system.name, value=swim(system), selected=system.id in query_params.system
                )
                for system in all_present_systems
            ],
            description="Find games using any of these systems:",
        ),
        "tone": MultiselectFormData(
            label="Tone",
            name="tone",
            options=[
                MultiselectFormDataOption(label=tone.value, value=tone.value, selected=tone.value in query_params.tone)
                for tone in all_tones
            ],
            description="Find games with any of these tones:",
        ),
        "bonus": MultiselectFormData(
            label="Bonus Features",
            name="bonus",
            options=[
                MultiselectFormDataOption(
                    label=bonus.notes[0], value=str(bonus.value), selected=bonus.value in query_params.bonus
                )
                for bonus in all_bonus
            ],
            description="Find games with any of these bonus features:",
        ),
        "content": MultiselectFormData(
            label="Exclude Content",
            name="content",
            options=[
                MultiselectFormDataOption(
                    label=content_warning.name,
                    value=swim(content_warning),
                    selected=content_warning.id in query_params.content,
                )
                for content_warning in all_present_content_warnings
            ],
            description='Find games <span class="text-warning font-semibold">EXCLUDING</span> any of these content warnings:',
        ),
    }


def user_can_manage_submissions(user: User, event: Event) -> bool:
    return user_has_permission(user, "event", (event, event), "manage_submissions")


@dataclass
class MultiselectFormDataOption:
    label: str
    value: str
    selected: bool = False


@dataclass
class MultiselectFormData:
    label: str
    name: str
    options: list[MultiselectFormDataOption]
    description: str | None = None


class PutEventManageScheduleSession(BaseModel):
    game: SqidInt
    table: SqidInt
    time_slot: SqidInt


class PutEventManageScheduleForm(BaseModel):
    sessions: list[PutEventManageScheduleSession]
    commit: bool = False


@dataclass
class EventScheduleEditState:
    last_saved: str | None = None
    last_saved_by: str | None = None


async def get_user_game_preferences(
    request: Request, transaction: AsyncSession, event: Event
) -> dict[int, UserGamePreferenceValue]:
    if request.user is None:
        return {}

    stmt = (
        select(UserGamePreference)
        .join(Game, UserGamePreference.game_id == Game.id)
        .where(UserGamePreference.user_id == request.user.id)
        .where(Game.event_id == event.id)
    )
    preferences = (await transaction.execute(stmt)).scalars().all()
    return {preference.game_id: preference.preference for preference in preferences}


class EventController(Controller):
    dependencies = {
        "event": event_with(),
    }

    @get(
        ["/event/{event_sqid:str}", "/event/{event_sqid:str}/games", "/games"],
        dependencies={
            "query_params": Provide(build_event_games_query),
            "games": Provide(get_event_approved_games_dep),
            "form_data": Provide(get_form_data),
            "preferences": Provide(get_user_game_preferences),
        },
    )
    async def get_event_games(
        self,
        request: Request,
        event: Event,
        games: Sequence[Game],
        preferences: dict[int, UserGamePreferenceValue],
        form_data: dict[str, MultiselectFormData],
    ) -> Template:
        return HTMXBlockTemplate(
            template_name="pages/event_games.html.jinja",
            block_name=request.htmx.target,
            context={
                "event": event,
                "games": games,
                "form_data": form_data,
                "preferences": preferences,
            },
        )

    @get(
        path="/event/{event_sqid:str}/manage-schedule",
        guards=[user_guard],
        dependencies={
            "event": event_with(
                selectinload(Event.games).options(
                    selectinload(Game.game_requirement).selectinload(GameRequirement.available_time_slots),
                    selectinload(Game.gamemaster),
                    selectinload(Game.sessions),
                ),
                selectinload(Event.rooms).selectinload(Room.tables),
                selectinload(Event.time_slots),
                selectinload(Event.tables),
                selectinload(Event.sessions).selectinload(Session.game),
            ),
            "permission": permission_check(user_can_manage_submissions),
        },
    )
    async def get_event_manage_schedule(
        self,
        request: Request,
        event: Event,
        permission: bool,
    ) -> Template:
        # Games duplicated by the number of times to run
        unscheduled_games = list(
            itertools.chain.from_iterable([game] * game.game_requirement.times_to_run for game in event.games)
        )

        # Remove games that have sessions already scheduled
        for session in event.sessions:
            # Only look for uncommitted sessions, since that's what we display to admins editing the current save
            if session.committed:
                continue
            # Remove one instance of the game from unscheduled games
            if session.game in unscheduled_games:
                unscheduled_games.remove(session.game)
            else:
                print("!!!! WARNING: Session game not found in unscheduled games - count mismatch", session.game.name)

        return HTMXBlockTemplate(
            template_name="pages/event_manage_schedule.html.jinja",
            block_name=request.htmx.target,
            context={
                "event": event,
                "unscheduled_games": unscheduled_games,
                "sessions_by_table_and_time_slot": {
                    (table.id, time_slot.id): [
                        session
                        for session in event.sessions
                        if session.table_id == table.id
                        and session.time_slot_id == time_slot.id
                        and not session.committed  # Only show uncommitted (but saved) sessions
                    ]
                    for table in event.tables
                    for time_slot in event.time_slots
                },
            },
        )

    @put(
        path="/event/{event_sqid:str}/manage-schedule",
        guards=[user_guard],
        dependencies={
            "event": event_with(
                selectinload(Event.sessions),
            ),
            "permission": permission_check(user_can_manage_submissions),
        },
    )
    async def put_event_manage_schedule(
        self,
        event: Event,
        permission: bool,
        transaction: AsyncSession,
        data: Annotated[PutEventManageScheduleForm, Body(media_type=RequestEncodingType.JSON)],
    ) -> Response[str]:
        print(data)
        # Set the event's sessions to the new data - including deleting any existing sessions
        new_sessions: list[Session] = []

        if not data.commit:
            # We are not committing, so don't remove existing committed sessions
            new_sessions = [s for s in event.sessions if s.committed]

        for session_data in data.sessions:
            new_sessions.append(
                Session(
                    game_id=session_data.game,
                    table_id=session_data.table,
                    time_slot_id=session_data.time_slot,
                    event_id=event.id,
                    committed=False,
                )
            )
            if data.commit:
                # Also add a committed session for the game
                new_sessions.append(
                    Session(
                        game_id=session_data.game,
                        table_id=session_data.table,
                        time_slot_id=session_data.time_slot,
                        event_id=event.id,
                        committed=True,
                    )
                )

        event.sessions = new_sessions

        # Save the event
        transaction.add(event)

        return Response(content="", status_code=HTTP_204_NO_CONTENT)

    @get(
        path="/event/{event_sqid:str}/manage-schedule/last-updated-by",
        guards=[user_guard],
        dependencies={
            "event": event_with(
                selectinload(Event.sessions).selectinload(Session.updated_by_user),
            ),
            "permission": permission_check(user_can_manage_submissions),
        },
    )
    async def get_event_manage_schedule_last_updated(
        self, event: Event, user: User, last_saved: Annotated[datetime | None, Parameter(query="last-saved")] = None
    ) -> Response[str]:
        current_time = datetime.now(tz=timezone.utc)

        last_saved_session = max(
            [s for s in event.sessions if not s.committed], key=lambda s: s.updated_at, default=None
        )
        last_save_updater = last_saved_session.updated_by_user if last_saved_session else None
        last_save_time = last_saved_session.updated_at if last_saved_session else None
        last_save_name_string = (
            "never"
            if last_save_updater is None
            else last_save_updater.full_name
            if user.id != last_save_updater.id
            else "you"
        )
        last_save_delta_string = "" if last_save_time is None else humanize.naturaltime(current_time - last_save_time)

        last_commit_session = max([s for s in event.sessions if s.committed], key=lambda s: s.updated_at, default=None)
        last_commit_updater = last_commit_session.updated_by_user if last_commit_session else None
        last_commit_time = last_commit_session.updated_at if last_commit_session else None
        last_commit_name_string = (
            "never"
            if last_commit_updater is None
            else last_commit_updater.full_name
            if user.id != last_commit_updater.id
            else "you"
        )
        last_commit_delta_string = (
            "" if last_commit_time is None else humanize.naturaltime(current_time - last_commit_time)
        )

        content = f"<span>Saved by {last_save_name_string} {last_save_delta_string}.</span><br><span>Committed by {last_commit_name_string} {last_commit_delta_string}.</span>"

        if last_saved is not None and last_save_time is not None and last_save_time > last_saved:
            content += "<br><span class='text-warning'>WARNING: This schedule has been updated since you last saved on this page, please review before saving or committing.</span>"

        return Response(
            content=content,
            status_code=HTTP_200_OK,
        )

    @get(
        path="/event/{event_sqid:str}/manage-submissions",
        guards=[user_guard],
        dependencies={
            "permission": permission_check(user_can_manage_submissions),
            "games": Provide(get_event_games_dep),
        },
    )
    async def get_event_manage_submissions(
        self,
        request: Request,
        event: Event,
        games: Sequence[Game],
        permission: bool,
        sort: Literal["title", "system", "gamemaster", "submitted", "status", "sessions"] = "submitted",
        desc: bool = False,
    ) -> Template:
        return HTMXBlockTemplate(
            template_name="pages/event_manage_submissions.html.jinja",
            block_name=request.htmx.target,
            context={
                "event": event,
                "games": games,
                "sort": sort,
                "desc": desc,
                "submission_status": SubmissionStatus,
                "total_games": len(games),
                "total_systems": len({game.system.id for game in games}),
                "total_gamemasters": len({game.gamemaster.id for game in games}),
                "total_sessions": sum([game.game_requirement.times_to_run for game in games]),
                "total_approved_sessions": sum(
                    [
                        game.game_requirement.times_to_run
                        for game in games
                        if game.submission_status == SubmissionStatus.APPROVED
                    ]
                ),
                "total_draft_sessions": sum(
                    [
                        game.game_requirement.times_to_run
                        for game in games
                        if game.submission_status == SubmissionStatus.DRAFT
                    ]
                ),
                "total_submitted_sessions": sum(
                    [
                        game.game_requirement.times_to_run
                        for game in games
                        if game.submission_status == SubmissionStatus.SUBMITTED
                    ]
                ),
                "total_rejected_sessions": sum(
                    [
                        game.game_requirement.times_to_run
                        for game in games
                        if game.submission_status == SubmissionStatus.REJECTED
                    ]
                ),
                "total_cancelled_sessions": sum(
                    [
                        game.game_requirement.times_to_run
                        for game in games
                        if game.submission_status == SubmissionStatus.CANCELLED
                    ]
                ),
            },
        )
