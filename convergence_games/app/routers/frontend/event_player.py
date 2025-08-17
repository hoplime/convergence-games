from __future__ import annotations

import datetime as dt
import zoneinfo
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal

from litestar import Controller, get
from litestar.di import Provide
from litestar.exceptions import HTTPException
from litestar.params import Parameter
from litestar.response import Template
from pydantic import BaseModel, BeforeValidator
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload
from sqlalchemy.sql.base import ExecutableOption
from sqlalchemy.sql.functions import coalesce

from convergence_games.app.guards import user_guard
from convergence_games.app.request_type import Request
from convergence_games.app.response_type import HTMXBlockTemplate
from convergence_games.db.enums import (
    GameClassification,
    GameKSP,
    GameTone,
    SubmissionStatus,
    TierValue,
    UserGamePreferenceValue,
)
from convergence_games.db.models import (
    ContentWarning,
    Event,
    Game,
    GameContentWarningLink,
    GameGenreLink,
    Genre,
    Party,
    PartyUserLink,
    Session,
    System,
    TimeSlot,
    User,
    UserGamePreference,
)
from convergence_games.db.ocean import Sqid, sink, swim

# region Data Schema
SqidInt = Annotated[int, BeforeValidator(sink)]


class EventGamesQuery(BaseModel):
    genre: list[SqidInt] = []
    system: list[SqidInt] = []
    tone: list[str] = []
    bonus: list[int] = []
    content: list[SqidInt] = []


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


async def event_games_query_from_params_dep(
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
        .where(Game.event_id == event.id)
    )
    preferences = (await transaction.execute(stmt)).scalars().all()
    return {preference.game_id: preference.preference for preference in preferences}


# endregion


class EventPlayerController(Controller):
    # Event viewing
    @get(
        ["/event/{event_sqid:str}", "/event/{event_sqid:str}/games", "/games"],
        dependencies={
            "event": event_with(),
            "query_params": Provide(event_games_query_from_params_dep),
            "games": Provide(get_event_approved_games_dep),
            "form_data": Provide(get_form_data_dep),
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
        ["/event/{event_sqid:str}/planner", "/event/{event_sqid:str}/planner/{time_slot_sqid:str}"],
        dependencies={"event": event_with(selectinload(Event.time_slots))},
        guards=[user_guard],
    )
    async def get_event_session_planner(
        self,
        request: Request,
        transaction: AsyncSession,
        event: Event,
        user: User,
        time_slot_sqid: Annotated[Sqid | None, Parameter()] = None,
    ) -> Template:
        time_slot: TimeSlot | None = None
        if time_slot_sqid is not None:
            time_slot_id = sink(time_slot_sqid)
            time_slot = next(
                (ts for ts in event.time_slots if ts.id == time_slot_id),
                None,
            )
        if time_slot is None:
            # Get the next upcoming time slot, or the last one if there are no upcoming slots
            # TODO: Do this based on completed/upcoming status in time slots - logic TODO after allocation is done
            # TODO: Also lock down changing party based on time slot status - UPCOMING (unlocked), ALLOCATING (locked), COMPLETED (locked)
            sorted_event_time_slots = sorted(event.time_slots, key=lambda ts: ts.start_time)
            # mock_time = datetime(2025, 9, 13, 15, 0, 0, tzinfo=zoneinfo.ZoneInfo(event.timezone))
            time_slot = next(
                (ts for ts in sorted_event_time_slots if ts.start_time > datetime.now(tz=dt.timezone.utc)),
                sorted_event_time_slots[-1],
            )

        PLinkThisUser = aliased(PartyUserLink)
        PLinkAllInParty = aliased(PartyUserLink)
        ThisUserPreference = aliased(UserGamePreference)
        LeaderUserPreference = aliased(UserGamePreference)

        party_members = list(
            (
                await transaction.execute(
                    (
                        select(User, PLinkAllInParty.is_leader)
                        .join(PLinkAllInParty, User.id == PLinkAllInParty.user_id)
                        .join(PLinkThisUser, PLinkAllInParty.party_id == PLinkThisUser.party_id)
                        .where(PLinkThisUser.user_id == user.id, PLinkThisUser.party.has(time_slot_id=time_slot.id))
                    )
                )
            ).all()
        )
        party_leader = next(
            (member_and_is_leader.t[0] for member_and_is_leader in party_members if member_and_is_leader.t[1]), user
        )
        all_party_members_over_18 = all(member_and_is_leader.t[0].over_18 for member_and_is_leader in party_members)

        select_terms = (
            (Game, ThisUserPreference.preference, LeaderUserPreference.preference)
            if party_leader.id != user.id
            else (Game, ThisUserPreference.preference, ThisUserPreference.preference)
        )

        games_and_preferences_this_time_slot_stmt = (
            select(*select_terms)
            .options(
                selectinload(Game.system),
                selectinload(Game.gamemaster),
                selectinload(Game.game_requirement),
                selectinload(Game.genres),
                selectinload(Game.content_warnings),
                selectinload(Game.event),
            )
            .join(Session, Session.game_id == Game.id)
            .where(
                (Session.time_slot_id == time_slot.id)
                & Session.committed
                & (Game.submission_status == SubmissionStatus.APPROVED)
            )
            .join(
                ThisUserPreference,
                and_(ThisUserPreference.game_id == Game.id, ThisUserPreference.user_id == user.id),
                isouter=True,
            )
        )

        if party_leader.id != user.id:
            games_and_preferences_this_time_slot_stmt = games_and_preferences_this_time_slot_stmt.join(
                LeaderUserPreference,
                and_(LeaderUserPreference.game_id == Game.id, LeaderUserPreference.user_id == party_leader.id),
                isouter=True,
            )

        games_and_preferences = (await transaction.execute(games_and_preferences_this_time_slot_stmt)).all()

        game_tier_dict: dict[TierValue, list[Game]] = {}
        preferences: dict[int, UserGamePreferenceValue] = {}
        for row in games_and_preferences:
            game, user_preference_value, leader_preference_value = row.tuple()
            # Get the personal preference
            preferences[game.id] = user_preference_value

            # Deal with the leader preference for tiering
            if leader_preference_value is None:  # pyright: ignore[reportUnnecessaryComparison]  # We actually can get None from the outer join with no coalesce for default
                leader_preference_value = UserGamePreferenceValue.D6
            tier_value = TierValue(leader_preference_value)
            if game.gamemaster_id == user.id:
                tier_value = TierValue.GM
            elif game.classification == GameClassification.R18 and not all_party_members_over_18:
                tier_value = TierValue.AGE_RESTRICTED
            if tier_value not in game_tier_dict:
                game_tier_dict[tier_value] = []
            game_tier_dict[tier_value].append(game)

        game_tier_list = sorted(game_tier_dict.items(), key=lambda item: item[0].value, reverse=True)

        return HTMXBlockTemplate(
            template_name="pages/event_session_planner.html.jinja",
            block_name=request.htmx.target,
            context={
                "event": event,
                "selected_time_slot": time_slot,
                "game_tier_list": game_tier_list,
                "preferences": preferences,
                "party_leader": party_leader,
                "all_party_members_over_18": all_party_members_over_18,
            },
        )
