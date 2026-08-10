from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Annotated, Literal

from litestar import Controller, get
from litestar.di import Provide
from litestar.response import Template
from pydantic import BaseModel, BeforeValidator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from convergence_games.db.enums import (
    GameKSP,
    GameTone,
    SubmissionStatus,
    UserGamePreferenceValue,
)
from convergence_games.db.models import (
    ContentWarning,
    Event,
    Game,
    GameContentWarningLink,
    GameGenreLink,
    Genre,
    Session,
    System,
    UserEventD20Transaction,
    UserGamePlayed,
    UserGamePreference,
)
from convergence_games.lib.deps import event_with
from convergence_games.lib.ocean import Sqid, sink, swim
from convergence_games.lib.request_type import Request
from convergence_games.lib.response_type import HTMXBlockTemplate

# region Data Schema
SqidInt = Annotated[int, BeforeValidator(sink)]


class EventGamesQuery(BaseModel):
    genre: list[SqidInt] = []
    system: list[SqidInt] = []
    tone: list[str] = []
    bonus: list[int] = []
    content: list[SqidInt] = []
    preference: list[Literal["unrated", "rated"]] = []
    session: list[SqidInt] = []


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


# endregion


# region Dependencies
async def get_event_approved_games_dep(
    event: Event,
    transaction: AsyncSession,
    query_params: EventGamesQuery,
    request: Request,
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
            selectinload(Game.event).selectinload(Event.time_slots),
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
    if request.user is not None and len(query_params.preference) == 1:
        if query_params.preference[0] == "unrated":
            # Where not exists a UserGamePreference
            stmt = stmt.where(
                ~select(UserGamePreference)
                .where(
                    (UserGamePreference.game_id == Game.id)
                    & (UserGamePreference.user_id == request.user.id)
                    & (UserGamePreference.frozen_at_time_slot_id.is_(None))
                )  # pyright: ignore[reportUnnecessaryComparison]  # We actually can get None from the outer join with no coalesce for default
                .exists()
            )
        else:
            stmt = stmt.join(UserGamePreference, UserGamePreference.game_id == Game.id).where(
                UserGamePreference.user_id == request.user.id
            )
    if query_params.session:
        stmt = stmt.join(Session, Session.game_id == Game.id).where(
            Session.time_slot_id.in_(query_params.session),
            Session.committed,
        )
    games = (await transaction.execute(stmt)).scalars().all()
    return games


async def event_games_query_from_params_dep(
    genre: list[Sqid] | None = None,
    system: list[Sqid] | None = None,
    tone: list[str] | None = None,
    bonus: list[int] | None = None,
    content: list[Sqid] | None = None,
    preference: list[Literal["unrated", "rated"]] | None = None,
    session: list[Sqid] | None = None,
) -> EventGamesQuery:
    return EventGamesQuery.model_validate(
        {
            "genre": genre or [],
            "system": system or [],
            "tone": tone or [],
            "bonus": bonus or [],
            "content": content or [],
            "preference": preference or [],
            "session": session or [],
        }
    )


async def get_form_data_dep(
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
            label="Bonus",
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
        "preference": MultiselectFormData(
            label="Preference",
            name="preference",
            options=[
                MultiselectFormDataOption(
                    label="Unrated",
                    value="unrated",
                    selected="unrated" in query_params.preference,
                ),
                MultiselectFormDataOption(
                    label="Rated",
                    value="rated",
                    selected="rated" in query_params.preference,
                ),
            ],
            description="Find games that you've not yet rated, or only games that you've rated:",
        ),
        "session": MultiselectFormData(
            label="Session",
            name="session",
            options=[
                MultiselectFormDataOption(
                    label=time_slot.name,
                    value=swim(time_slot),
                    selected=time_slot.id in query_params.session,
                )
                for time_slot in sorted(event.time_slots, key=lambda ts: ts.start_time)
            ],
            description="Find games scheduled for any of these session times:",
        ),
    }


async def get_user_game_preferences(
    request: Request, transaction: AsyncSession, event: Event
) -> dict[int, UserGamePreferenceValue]:
    if request.user is None:
        return {}

    stmt = (
        select(UserGamePreference)
        .join(Game, UserGamePreference.game_id == Game.id)
        .where(UserGamePreference.user_id == request.user.id)
        .where(UserGamePreference.frozen_at_time_slot_id.is_(None))
        .where(Game.event_id == event.id)
    )
    preferences = (await transaction.execute(stmt)).scalars().all()
    return {preference.game_id: preference.preference for preference in preferences}


async def get_user_game_playeds(request: Request, transaction: AsyncSession, event: Event) -> dict[int, UserGamePlayed]:
    if request.user is None:
        return {}

    stmt = (
        select(UserGamePlayed)
        .join(Game, UserGamePlayed.game_id == Game.id)
        .where(UserGamePlayed.user_id == request.user.id)
        .where(Game.event_id == event.id)
    )
    user_game_playeds = (await transaction.execute(stmt)).scalars().all()
    return {user_game_played.game_id: user_game_played for user_game_played in user_game_playeds}


# endregion


class EventGamesController(Controller):
    @get(
        ["/event/{event_sqid:str}", "/event/{event_sqid:str}/games"],
        dependencies={
            "event": event_with(selectinload(Event.time_slots)),
            "query_params": Provide(event_games_query_from_params_dep),
            "games": Provide(get_event_approved_games_dep),
            "form_data": Provide(get_form_data_dep),
            "preferences": Provide(get_user_game_preferences),
            "user_game_playeds": Provide(get_user_game_playeds),
        },
    )
    async def get_event_games(
        self,
        request: Request,
        event: Event,
        games: Sequence[Game],
        preferences: dict[int, UserGamePreferenceValue],
        user_game_playeds: dict[int, UserGamePlayed],
        form_data: dict[str, MultiselectFormData],
        transaction: AsyncSession,
    ) -> Template:
        scheduled_time_slots_stmt = select(Session.game_id, Session.time_slot_id).where(Session.committed)
        scheduled_time_slots = (await transaction.execute(scheduled_time_slots_stmt)).all()
        scheduled_time_slots_dict: dict[int, list[int]] = {}
        for r in scheduled_time_slots:
            game_id, time_slot_id = r.tuple()
            if game_id not in scheduled_time_slots_dict:
                scheduled_time_slots_dict[game_id] = []
            scheduled_time_slots_dict[game_id].append(time_slot_id)

        if request.user:
            latest_d20_transaction = (
                await transaction.execute(
                    select(UserEventD20Transaction)
                    .where(UserEventD20Transaction.user_id == request.user.id)
                    .where(UserEventD20Transaction.event_id == event.id)
                    .order_by(UserEventD20Transaction.id.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
        else:
            latest_d20_transaction = None

        return HTMXBlockTemplate(
            template_name="pages/event_games.html.jinja",
            block_name=request.htmx.target,
            context={
                "event": event,
                "games": games,
                "form_data": form_data,
                "preferences": preferences,
                "user_game_playeds": user_game_playeds,
                "scheduled_time_slots": scheduled_time_slots_dict,
                "latest_d20_transaction": latest_d20_transaction,
            },
        )

