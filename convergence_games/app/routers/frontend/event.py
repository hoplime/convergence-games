from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Annotated, Literal

from litestar import Controller, get
from litestar.di import Provide
from litestar.exceptions import HTTPException
from pydantic import BaseModel, BeforeValidator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from convergence_games.app.guards import permission_check, user_guard
from convergence_games.app.request_type import Request
from convergence_games.app.response_type import HTMXBlockTemplate, Template
from convergence_games.db.enums import GameKSP, GameTone, SubmissionStatus
from convergence_games.db.models import (
    ContentWarning,
    Event,
    Game,
    GameContentWarningLink,
    GameGenreLink,
    Genre,
    System,
    User,
)
from convergence_games.db.ocean import Sqid, sink, swim
from convergence_games.permissions import user_has_permission


async def get_event_dep(
    transaction: AsyncSession,
    event_sqid: Sqid | None = None,
) -> Event:
    event_id: int = sink(event_sqid) if event_sqid is not None else 1
    stmt = select(Event).where(Event.id == event_id)
    event = (await transaction.execute(stmt)).scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


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


class EventController(Controller):
    dependencies = {
        "event": Provide(get_event_dep),
    }

    @get(
        ["/event/{event_sqid:str}", "/event/{event_sqid:str}/games", "/games"],
        dependencies={
            "query_params": Provide(build_event_games_query),
            "games": Provide(get_event_approved_games_dep),
            "form_data": Provide(get_form_data),
        },
    )
    async def get_event_games(
        self,
        request: Request,
        event: Event,
        games: Sequence[Game],
        form_data: dict[str, MultiselectFormData],
    ) -> Template:
        return HTMXBlockTemplate(
            template_name="pages/event_games.html.jinja",
            block_name=request.htmx.target,
            context={
                "event": event,
                "games": games,
                "form_data": form_data,
            },
        )

    @get(
        path="/event/{event_sqid:str}/manage-schedule",
        guards=[user_guard],
        dependencies={
            "permission": permission_check(user_can_manage_submissions),
        },
    )
    async def get_event_manage_schedule(
        self,
        request: Request,
        event: Event,
        permission: bool,
    ) -> Template:
        return HTMXBlockTemplate(
            template_name="pages/event_manage_schedule.html.jinja",
            block_name=request.htmx.target,
            context={
                "event": event,
            },
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
