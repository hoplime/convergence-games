from __future__ import annotations

import datetime as dt
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
from sqlalchemy.orm import aliased, selectinload, with_loader_criteria
from sqlalchemy.sql.base import ExecutableOption

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
    PartyUserLink,
    Session,
    System,
    Table,
    TimeSlot,
    User,
    UserEventD20Transaction,
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
                .where((UserGamePreference.game_id == Game.id) & (UserGamePreference.user_id == request.user.id))
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
            "event": event_with(selectinload(Event.time_slots)),
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
                "scheduled_time_slots": scheduled_time_slots_dict,
                "latest_d20_transaction": latest_d20_transaction,
            },
        )

    @get(
        ["/event/{event_sqid:str}/planner", "/event/{event_sqid:str}/planner/{time_slot_sqid:str}", "/planner"],
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

        latest_d20_transaction = (
            await transaction.execute(
                select(UserEventD20Transaction)
                .where(UserEventD20Transaction.user_id == user.id)
                .where(UserEventD20Transaction.event_id == event.id)
                .order_by(UserEventD20Transaction.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

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
                        .options(
                            selectinload(User.latest_d20_transaction),
                            with_loader_criteria(UserEventD20Transaction, UserEventD20Transaction.event_id == event.id),
                        )
                    )
                )
            ).all()
        )
        party_leader = next(
            (member_and_is_leader.t[0] for member_and_is_leader in party_members if member_and_is_leader.t[1]), user
        )
        all_party_members_over_18 = all(member_and_is_leader.t[0].over_18 for member_and_is_leader in party_members)
        all_party_members_have_d20 = all(
            (
                member_and_is_leader.t[0].latest_d20_transaction is not None
                and member_and_is_leader.t[0].latest_d20_transaction.current_balance > 0
            )
            for member_and_is_leader in party_members
        )
        if not party_members:
            all_party_members_over_18 = user.over_18
            all_party_members_have_d20 = (
                latest_d20_transaction is not None and latest_d20_transaction.current_balance > 0
            )

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
        scheduled_time_slots_stmt = select(Session.game_id, Session.time_slot_id).where(Session.committed)
        scheduled_time_slots = (await transaction.execute(scheduled_time_slots_stmt)).all()
        scheduled_time_slots_dict: dict[int, list[int]] = {}
        for r in scheduled_time_slots:
            game_id, time_slot_id = r.tuple()
            if game_id not in scheduled_time_slots_dict:
                scheduled_time_slots_dict[game_id] = []
            scheduled_time_slots_dict[game_id].append(time_slot_id)

        game_tier_dict: dict[TierValue, list[Game]] = {}
        preferences: dict[int, UserGamePreferenceValue] = {}
        downgraded_d20: bool = False
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
            elif tier_value == TierValue.D20 and not all_party_members_have_d20:
                tier_value = TierValue.D12
                if party_leader.id == user.id:
                    downgraded_d20 = True

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
                "scheduled_time_slots": scheduled_time_slots_dict,
                "has_d20": latest_d20_transaction is not None and latest_d20_transaction.current_balance > 0,
                "all_party_members_have_d20": all_party_members_have_d20,
                "downgraded_d20": downgraded_d20,
            },
        )
