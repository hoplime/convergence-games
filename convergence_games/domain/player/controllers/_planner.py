from __future__ import annotations

import datetime as dt
from datetime import datetime
from typing import Annotated

from litestar import Controller, get
from litestar.params import Parameter
from litestar.response import Template
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload, with_loader_criteria

from convergence_games.db.enums import (
    GameClassification,
    SubmissionStatus,
    TierValue,
    UserGamePreferenceValue,
)
from convergence_games.db.models import (
    Event,
    Game,
    PartyUserLink,
    Session,
    TimeSlot,
    User,
    UserEventD20Transaction,
    UserGamePlayed,
    UserGamePreference,
)
from convergence_games.lib.deps import event_with
from convergence_games.lib.guards import user_guard
from convergence_games.lib.ocean import Sqid, sink
from convergence_games.lib.permissions import user_has_permission
from convergence_games.lib.request_type import Request
from convergence_games.lib.response_type import HTMXBlockTemplate


class PlannerController(Controller):
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
        if not event.is_planner_open() and not user_has_permission(
            user, "event", (event, event), "manage_submissions"
        ):
            return HTMXBlockTemplate(
                template_name="pages/event_planner_closed.html.jinja",
                block_name=request.htmx.target,
                context={"event": event},
            )

        time_slot: TimeSlot | None = None
        if time_slot_sqid is not None:
            time_slot_id = sink(time_slot_sqid)
            time_slot = next(
                (ts for ts in event.time_slots if ts.id == time_slot_id),
                None,
            )

        if time_slot is None:
            sorted_event_time_slots = sorted(event.time_slots, key=lambda ts: ts.start_time)
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

        PLinkThisUser = aliased(PartyUserLink)  # noqa: N806
        PLinkAllInParty = aliased(PartyUserLink)  # noqa: N806
        ThisUserPreference = aliased(UserGamePreference)  # noqa: N806
        LeaderUserPreference = aliased(UserGamePreference)  # noqa: N806

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
                and_(
                    ThisUserPreference.game_id == Game.id,
                    ThisUserPreference.user_id == user.id,
                    ThisUserPreference.frozen_at_time_slot_id.is_(None),
                ),
                isouter=True,
            )
        )

        if party_leader.id != user.id:
            games_and_preferences_this_time_slot_stmt = games_and_preferences_this_time_slot_stmt.join(
                LeaderUserPreference,
                and_(
                    LeaderUserPreference.game_id == Game.id,
                    LeaderUserPreference.user_id == party_leader.id,
                    LeaderUserPreference.frozen_at_time_slot_id.is_(None),
                ),
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

        all_party_members_game_playeds_stmt = (
            select(UserGamePlayed)
            .join(Game, UserGamePlayed.game_id == Game.id)
            .where(
                UserGamePlayed.user_id.in_([member.t[0].id for member in party_members] if party_members else [user.id])
            )
            .where(Game.event_id == event.id)
        )
        all_party_members_game_playeds = (
            (await transaction.execute(all_party_members_game_playeds_stmt)).scalars().all()
        )
        user_game_playeds: dict[int, UserGamePlayed] = {
            user_game_played.game_id: user_game_played
            for user_game_played in all_party_members_game_playeds
            if user_game_played.user_id == user.id
        }
        any_party_member_has_played_and_wont_repeat: set[int] = {
            user_game_played.game_id
            for user_game_played in all_party_members_game_playeds
            if not user_game_played.allow_play_again
        }

        game_tier_dict: dict[TierValue, list[Game]] = {}
        preferences: dict[int, UserGamePreferenceValue] = {}
        downgraded_d20: bool = False
        for row in games_and_preferences:
            game, user_preference_value, leader_preference_value = row.tuple()

            preferences[game.id] = user_preference_value

            if leader_preference_value is None:  # pyright: ignore[reportUnnecessaryComparison]
                leader_preference_value = UserGamePreferenceValue.D6
            tier_value = TierValue(leader_preference_value)

            if game.gamemaster_id == user.id:
                tier_value = TierValue.GM
            elif game.id in any_party_member_has_played_and_wont_repeat:
                tier_value = TierValue.ALREADY_PLAYED
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
                "user_game_playeds": user_game_playeds,
                "party_leader": party_leader,
                "all_party_members_over_18": all_party_members_over_18,
                "scheduled_time_slots": scheduled_time_slots_dict,
                "has_d20": latest_d20_transaction is not None and latest_d20_transaction.current_balance > 0,
                "all_party_members_have_d20": all_party_members_have_d20,
                "any_party_member_has_played_and_wont_repeat": any_party_member_has_played_and_wont_repeat,
                "downgraded_d20": downgraded_d20,
            },
        )
