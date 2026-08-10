import datetime as dt
import itertools
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Annotated, Any, Literal, TypedDict, cast

from litestar import Controller, get, post, put
from litestar.exceptions import HTTPException
from litestar.params import Body, Parameter, RequestEncodingType
from litestar.response import Redirect, Response, Template
from litestar.status_codes import HTTP_204_NO_CONTENT
from pydantic import BaseModel
from rich.pretty import pprint
from sqlalchemy import bindparam, delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload, with_loader_criteria
from sqlalchemy.sql.selectable import Select

from convergence_games.db.enums import GameClassification, TimeSlotStatus
from convergence_games.db.models import (
    Allocation,
    Event,
    Game,
    Party,
    PartyUserLink,
    Session,
    Table,
    TimeSlot,
    User,
    UserCheckinStatus,
    UserEventCompensationTransaction,
    UserEventD20Transaction,
    UserGamePlayed,
    UserGamePreference,
)
from convergence_games.lib.context import user_id_ctx
from convergence_games.lib.deps import event_with
from convergence_games.lib.guards import permission_check, user_guard
from convergence_games.lib.ocean import Sqid, sink, swim
from convergence_games.lib.request_type import Request
from convergence_games.lib.response_type import HTMXBlockTemplate
from convergence_games.services.algorithm.game_allocator import (
    AlgPartyP,
    GameAllocator,
    calculate_compensation,
    generate_tier_list,
)
from convergence_games.services.algorithm.models import AlgResult
from convergence_games.services.algorithm.query_adapter import (
    adapt_results_to_database,
    adapt_to_inputs,
    user_preferences_to_alg_preferences,
)

from .._common import SqidInt, user_can_manage_submissions


class TierAsDict(TypedDict):
    is_d20: bool
    tier: int


class AllocationPartyMetadata(BaseModel):
    gm_of: list[Sqid] = []
    tiers: dict[Sqid, TierAsDict] = {}


class PutEventManageAllocationSession(BaseModel):
    leader: SqidInt
    session: SqidInt | None


class PutEventManageAllocationForm(BaseModel):
    allocations: list[PutEventManageAllocationSession]
    commit: bool = False


class AllocationController(Controller):
    guards = [user_guard]
    dependencies = {
        "event": event_with(selectinload(Event.time_slots)),
        "permission": permission_check(user_can_manage_submissions),
    }

    @get(
        path=[
            "/event/{event_sqid:str}/manage-allocation",
            "/event/{event_sqid:str}/manage-allocation/{time_slot_sqid:str}",
        ],
    )
    async def get_event_manage_allocation(
        self,
        request: Request,
        transaction: AsyncSession,
        event: Event,
        permission: bool,
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
            # 60 minute buffer on top of start time in case allocation starts later than the start time
            # And also so it's still the default time slot after the start time so people can see what game they are in
            sorted_event_time_slots = sorted(event.time_slots, key=lambda ts: ts.start_time)
            time_slot = next(
                (
                    ts
                    for ts in sorted_event_time_slots
                    if (ts.start_time + timedelta(minutes=60)) > datetime.now(tz=dt.timezone.utc)
                ),
                sorted_event_time_slots[-1],
            )

        sessions_stmt = (
            select(Session)
            .where(Session.time_slot_id == time_slot.id, Session.committed)
            .join(Table, Table.id == Session.table_id)
            .options(
                selectinload(Session.game),
                selectinload(Session.table),
            )
            .order_by(Table.name)
        )
        sessions = (await transaction.execute(sessions_stmt)).scalars().all()
        sessions_by_gm_id: dict[int, list[Sqid]] = {}
        for session in sessions:
            sessions_by_gm_id.setdefault(session.game.gamemaster_id, []).append(swim(session))

        party_subq = (
            select(Party, PartyUserLink)
            .join(Party, Party.id == PartyUserLink.party_id, isouter=True)
            .where(Party.time_slot_id == time_slot.id)
            .subquery()
        )
        party_alias = aliased(Party, party_subq)
        party_user_link_alias = aliased(PartyUserLink, party_subq)

        solo_players_and_leaders_stmt = cast(
            Select[tuple[User, Party | None, UserCheckinStatus | None, Allocation | None]],
            (
                select(User, party_alias, UserCheckinStatus, Allocation)
                .select_from(User)
                .join(party_subq, (party_user_link_alias.user_id == User.id), isouter=True)
                .join(
                    UserCheckinStatus,
                    (UserCheckinStatus.user_id == User.id) & (UserCheckinStatus.time_slot_id == time_slot.id),
                    isouter=True,
                )
                .join(
                    Allocation,
                    (Allocation.party_leader_id == User.id)
                    & (Allocation.session.has(time_slot_id=time_slot.id) & (~Allocation.committed)),
                    isouter=True,
                )
                .where(party_user_link_alias.is_leader | (party_alias.id.is_(None)))
                .options(
                    selectinload(User.all_game_preferences),
                    selectinload(User.latest_d20_transaction),
                    selectinload(User.games_played),
                    selectinload(party_alias.members).options(
                        selectinload(User.latest_d20_transaction), selectinload(User.games_played)
                    ),
                    with_loader_criteria(
                        UserGamePreference, UserGamePreference.frozen_at_time_slot_id.in_([time_slot.id, None])
                    ),
                )
            ),
        )
        groups = [r.tuple() for r in (await transaction.execute(solo_players_and_leaders_stmt)).all()]
        group_dict: dict[
            int | None, list[tuple[User, Party | None, UserCheckinStatus | None, AllocationPartyMetadata]]
        ] = {}
        for user, party, user_checkin_status, allocation in groups:
            has_d20 = (
                all(
                    member.latest_d20_transaction.current_balance > 0
                    if member.latest_d20_transaction is not None
                    else False
                    for member in party.members
                )
                if party is not None
                else (user.latest_d20_transaction is not None and user.latest_d20_transaction.current_balance > 0)
            )
            allocated_session_id = None if allocation is None else allocation.session_id
            # game_id -> UserGamePreference
            # We need to get the frozen preference for this time slot if it exists, otherwise the current preference
            allocated_or_current_game_preferences: dict[int, UserGamePreference] = {}

            for ugp in user.all_game_preferences:
                if (
                    ugp.frozen_at_time_slot_id == time_slot.id
                    or ugp.game_id not in allocated_or_current_game_preferences
                ):
                    # Current preference
                    allocated_or_current_game_preferences[ugp.game_id] = ugp

            # Already played
            already_played_games = {gp.game_id for gp in user.games_played if not gp.allow_play_again}
            if party is not None:
                for member in party.members:
                    already_played_games.update({gp.game_id for gp in member.games_played if not gp.allow_play_again})
                over_18 = all(member.over_18 for member in party.members)
            else:
                over_18 = user.over_18

            tier_list = generate_tier_list(
                user_preferences_to_alg_preferences(
                    list(allocated_or_current_game_preferences.values()),
                    has_d20,
                    [(s.id, s.game_id, s.game.classification == GameClassification.R18) for s in sessions],
                    already_played_games,
                    over_18=over_18,
                )
            )
            tiers: dict[Sqid, TierAsDict] = {
                swim("Session", session_id): cast(TierAsDict, asdict(tier))  # pyright: ignore[reportInvalidCast]
                for tier, session_ids in tier_list
                for session_id in session_ids
            }
            gm_of = sessions_by_gm_id.get(user.id, [])
            metadata = AllocationPartyMetadata(gm_of=gm_of, tiers=tiers)
            group_dict.setdefault(allocated_session_id, []).append((user, party, user_checkin_status, metadata))

        if None in group_dict:
            # Sort the unallocated groups by checked in and then by user full name
            group_dict[None] = sorted(
                group_dict[None], key=lambda tup: (tup[2] is None or not tup[2].checked_in, tup[0].full_name)
            )

        any_existing_compensation = (
            await transaction.execute(
                select(UserEventCompensationTransaction)
                .where(UserEventCompensationTransaction.event_id == event.id)
                .where(UserEventCompensationTransaction.associated_time_slot_id == time_slot.id)
                .limit(1)
            )
        ).scalar_one_or_none() is not None

        return HTMXBlockTemplate(
            template_name="pages/event_manage_allocation.html.jinja",
            block_name=request.htmx.target,
            context={
                "event": event,
                "selected_time_slot": time_slot,
                "compensated": "Compensated" if any_existing_compensation else "Uncompensated",
                "sessions": sessions,
                "groups": group_dict,
            },
        )

    @post(
        path="/event/{event_sqid:str}/manage-allocation/{time_slot_sqid:str}/do-allocation",
    )
    async def post_event_do_allocation(
        self,
        request: Request,
        transaction: AsyncSession,
        event: Event,
        permission: bool,
        time_slot_sqid: Annotated[Sqid, Parameter()],
    ) -> Redirect:
        time_slot_id = sink(time_slot_sqid)

        # Store all current user game preferences in the database, upserting as needed
        # These are the inputs to the algorithm, frozen
        insert_user_game_preferences_stmt = insert(UserGamePreference).from_select(
            [
                "preference",
                "game_id",
                "user_id",
                "frozen_at_time_slot_id",
            ],
            select(
                UserGamePreference.preference,
                UserGamePreference.game_id,
                UserGamePreference.user_id,
                bindparam("frozen_at_time_slot_id", time_slot_id).label("frozen_at_time_slot_id"),
            ).where(UserGamePreference.frozen_at_time_slot_id.is_(None)),
        )
        insert_user_game_preferences_update_stmt = insert_user_game_preferences_stmt.on_conflict_do_update(
            index_elements=(
                UserGamePreference.game_id,
                UserGamePreference.user_id,
                UserGamePreference.frozen_at_time_slot_id,
            ),
            set_={
                UserGamePreference.preference: insert_user_game_preferences_stmt.excluded.preference,
                UserGamePreference.updated_at: dt.datetime.now(tz=dt.timezone.utc),
                UserGamePreference.updated_by: user_id_ctx.get(),
            },
        )
        _ = await transaction.execute(insert_user_game_preferences_update_stmt)

        sessions, parties = await adapt_to_inputs(transaction, time_slot_id)
        game_allocator = GameAllocator(max_iterations=5000, debug_print=False)
        alg_results, compensation = game_allocator.allocate(sessions, parties, False)
        pprint(alg_results)
        pprint(compensation)
        await adapt_results_to_database(transaction, time_slot_id, alg_results, compensation)

        return Redirect(f"/event/{swim(event)}/manage-allocation/{time_slot_sqid}")

    @post(
        path="/event/{event_sqid:str}/manage-allocation/{time_slot_sqid:str}/unlock",
    )
    async def post_event_unlock_allocation(
        self,
        transaction: AsyncSession,
        permission: bool,
        event: Event,
        time_slot_sqid: Annotated[Sqid, Parameter()],
    ) -> str:
        time_slot_id = sink(time_slot_sqid)

        # Set the time slot status
        time_slot_id = sink(time_slot_sqid)
        time_slot = next(
            (ts for ts in event.time_slots if ts.id == time_slot_id),
            None,
        )

        if time_slot is None:
            raise HTTPException(status_code=404, detail="Time slot not found")

        time_slot.status = TimeSlotStatus.PRE_ALLOCATION

        transaction.add(time_slot)

        return TimeSlotStatus.PRE_ALLOCATION.value

    @post(
        path="/event/{event_sqid:str}/manage-allocation/{time_slot_sqid:str}/lock",
    )
    async def post_event_lock_allocation(
        self,
        transaction: AsyncSession,
        permission: bool,
        event: Event,
        time_slot_sqid: Annotated[Sqid, Parameter()],
    ) -> str:
        time_slot_id = sink(time_slot_sqid)

        # Set the time slot status
        time_slot_id = sink(time_slot_sqid)
        time_slot = next(
            (ts for ts in event.time_slots if ts.id == time_slot_id),
            None,
        )

        if time_slot is None:
            raise HTTPException(status_code=404, detail="Time slot not found")

        time_slot.status = TimeSlotStatus.ALLOCATING

        transaction.add(time_slot)

        return TimeSlotStatus.ALLOCATING.value

    @post(
        path="/event/{event_sqid:str}/manage-allocation/{time_slot_sqid:str}/{user_sqid:str}/checkin",
    )
    async def post_event_checkin_player(
        self,
        transaction: AsyncSession,
        permission: bool,
        event: Event,
        time_slot_sqid: Annotated[Sqid, Parameter()],
        user_sqid: Annotated[Sqid, Parameter()],
        data: Annotated[dict[Literal["checkin"], Literal["on"]], Body(media_type=RequestEncodingType.URL_ENCODED)],
    ) -> str:
        time_slot_id = sink(time_slot_sqid)
        user_id = sink(user_sqid)

        checkin_status = (
            (
                await transaction.execute(
                    select(UserCheckinStatus).where(
                        UserCheckinStatus.user_id == user_id, UserCheckinStatus.time_slot_id == time_slot_id
                    )
                )
            )
            .scalars()
            .one_or_none()
        )
        should_checkin = data.get("checkin", "off") == "on"

        if checkin_status is None:
            checkin_status = UserCheckinStatus(user_id=user_id, time_slot_id=time_slot_id, checked_in=should_checkin)
        else:
            checkin_status.checked_in = should_checkin

        transaction.add(checkin_status)

        return "checked-in"

    @put(
        path="/event/{event_sqid:str}/manage-allocation/{time_slot_sqid:str}",
    )
    async def put_event_manage_allocation(
        self,
        request: Request,
        transaction: AsyncSession,
        permission: bool,
        event: Event,
        time_slot_sqid: Annotated[Sqid, Parameter()],
        data: Annotated[PutEventManageAllocationForm, Body(media_type=RequestEncodingType.JSON)],
    ) -> Response[str]:
        time_slot = next(
            (ts for ts in event.time_slots if ts.id == sink(time_slot_sqid)),
            None,
        )

        if time_slot is None:
            raise HTTPException(status_code=404, detail="Time slot not found")

        # Update the allocations to match the new data
        new_allocations: list[Allocation] = []

        for allocation_data in data.allocations:
            if allocation_data.session is None:
                # No session allocated, skip
                # This'll go to overflow
                continue

            new_allocations.append(
                Allocation(
                    party_leader_id=allocation_data.leader,
                    session_id=allocation_data.session,
                    committed=False,
                )
            )

            if data.commit:
                # Also add a committed allocation for the party leader
                new_allocations.append(
                    Allocation(
                        party_leader_id=allocation_data.leader,
                        session_id=allocation_data.session,
                        committed=True,
                    )
                )

        time_slot.status = TimeSlotStatus.ALLOCATED if data.commit else TimeSlotStatus.ALLOCATING
        transaction.add(time_slot)

        # Remove existing allocations for this time slot
        delete_existing_allocations_stmt = delete(Allocation).where(
            Allocation.session.has(time_slot_id=sink(time_slot_sqid))
        )
        _ = await transaction.execute(delete_existing_allocations_stmt)

        # Add new allocations
        transaction.add_all(new_allocations)

        return Response(content="", status_code=HTTP_204_NO_CONTENT)

    @put(
        path="/event/{event_sqid:str}/manage-allocation/{time_slot_sqid:str}/apply-compensation",
    )
    async def put_event_apply_compensation(
        self,
        request: Request,
        transaction: AsyncSession,
        permission: bool,
        event: Event,
        time_slot_sqid: Annotated[Sqid, Parameter()],
    ) -> str:
        time_slot_id = sink(time_slot_sqid)

        sessions, parties = await adapt_to_inputs(transaction, time_slot_id)
        parties = [AlgPartyP.from_alg_party(p) for p in parties]

        # TODO: Extract common functionality
        party_subq = (
            select(Party, PartyUserLink)
            .join(Party, Party.id == PartyUserLink.party_id, isouter=True)
            .where(Party.time_slot_id == time_slot_id)
            .subquery()
        )
        party_alias = aliased(Party, party_subq)
        party_user_link_alias = aliased(PartyUserLink, party_subq)
        solo_players_and_leaders_stmt = cast(
            Select[tuple[User, Party | None, Allocation | None, int | None]],
            (
                select(User, party_alias, Allocation, Game.gamemaster_id)
                .select_from(User)
                # Join party and user link, only leaders and solo players
                .join(party_subq, (party_user_link_alias.user_id == User.id), isouter=True)
                .where(party_user_link_alias.is_leader | (party_alias.id.is_(None)))
                # Is checked in
                .join(
                    UserCheckinStatus,
                    (UserCheckinStatus.user_id == User.id) & (UserCheckinStatus.time_slot_id == time_slot_id),
                )
                .where(UserCheckinStatus.checked_in)
                .join(
                    Allocation,
                    (Allocation.party_leader_id == User.id)
                    & (Allocation.session.has(time_slot_id=time_slot_id) & (~Allocation.committed)),
                    isouter=True,
                )
                # Include game to get if is GM
                .join(Session, Session.id == Allocation.session_id, isouter=True)
                .join(Game, Game.id == Session.game_id, isouter=True)
                .options(
                    selectinload(party_alias.members),
                )
            ),
        )
        allocations = [r.tuple() for r in (await transaction.execute(solo_players_and_leaders_stmt)).all()]
        gm_user_ids_this_session_stmt = (
            select(Session.id, Session.game_id, Game.gamemaster_id)
            .select_from(Session)
            .join(Game, (Session.time_slot_id == time_slot_id) & (Session.game_id == Game.id) & (Session.committed))
        )
        gm_user_ids_this_session = [r.tuple() for r in (await transaction.execute(gm_user_ids_this_session_stmt)).all()]
        session_game_id_map = {r[0]: r[1] for r in gm_user_ids_this_session}
        session_gm_id_map = {r[0]: r[2] for r in gm_user_ids_this_session}
        party_member_mapping: dict[int, list[int]] = {
            user.id: [member.id for member in party.members] if party is not None else [user.id]
            for user, party, *_ in allocations
        }
        all_user_ids = list(itertools.chain.from_iterable(party_member_mapping.values()))
        assert len(all_user_ids) == len(set(all_user_ids)), "Duplicate user IDs in party member mapping"

        # SHARED INFORMATION - RESULTS AND COMPENSATION
        results: list[AlgResult] = [
            AlgResult(
                party_leader_id=("GM" if party_leader.id in session_gm_id_map.values() else "USER", party_leader.id),
                session_id=allocation.session_id if allocation is not None else None,
                assignment_type="GM" if party_leader.id == gamemaster_id else "PLAYER",
            )
            for party_leader, _, allocation, gamemaster_id in allocations
        ]
        compensation = calculate_compensation(sessions, parties, results)
        print(compensation)

        # SHARED INFORMATION - EXISTING TRANSACTIONS
        transaction.expunge_all()
        existing_compensations_and_d20_users = (
            (
                await transaction.execute(
                    select(User)
                    .where(User.id.in_(all_user_ids))
                    .options(
                        selectinload(User.latest_compensation_transaction),
                        selectinload(User.latest_d20_transaction),
                        with_loader_criteria(
                            UserEventCompensationTransaction,
                            UserEventCompensationTransaction.event_id == event.id,
                        ),
                        with_loader_criteria(
                            UserEventD20Transaction,
                            UserEventD20Transaction.event_id == event.id,
                        ),
                    )
                )
            )
            .scalars()
            .all()
        )
        existing_compensation_map = {
            user.id: user.latest_compensation_transaction for user in existing_compensations_and_d20_users
        }

        # COMPENSATION
        # TODO: Undo any existing compensation for this time slot?
        # Not critical if we only hit this once :)
        total_compensations: dict[int, int] = {}
        for party_leader_id, total_compensation in compensation.party_compensations.items():
            if party_leader_id[0] == "OVERFLOW":
                continue
            party_members = party_member_mapping[party_leader_id[1]]
            for member_id in party_members:
                if total_compensation >= 0:
                    total_compensations[member_id] = total_compensation // len(party_members)
                else:
                    # Negative compensation, reset everyone to zero
                    current_comp = existing_compensation_map.get(member_id)
                    total_compensations[member_id] = -current_comp.current_balance if current_comp is not None else 0
        for session_id, total_compensation in compensation.session_compensations.items():
            if session_id is None:
                continue
            gm_id = session_gm_id_map.get(session_id)
            if gm_id is None:
                continue
            total_compensations[gm_id] += total_compensation

        new_compensations = [
            UserEventCompensationTransaction(
                current_balance=d20s.current_balance + total_compensation,
                previous_balance=d20s.current_balance,
                delta=total_compensation,
                event_id=event.id,
                user_id=user_id,
                previous_transaction_id=d20s.id,
                associated_time_slot_id=time_slot_id,
            )
            if user_id in existing_compensation_map and (d20s := existing_compensation_map[user_id]) is not None
            else UserEventCompensationTransaction(
                current_balance=total_compensation,
                previous_balance=0,
                delta=total_compensation,
                event_id=event.id,
                user_id=user_id,
                previous_transaction_id=None,
                associated_time_slot_id=time_slot_id,
            )
            # for party_leader_id, members in party_member_mapping.items()
            for user_id, total_compensation in total_compensations.items()
        ]

        transaction.add_all(new_compensations)

        # D20s
        total_d20s_spent: dict[int, int] = {}
        for result in results:
            party_members = party_member_mapping[result.party_leader_id[1]]
            for member_id in party_members:
                total_d20s_spent[member_id] = compensation.d20s_spent.get(result.party_leader_id, 0)
        existing_d20_map = {user.id: user.latest_d20_transaction for user in existing_compensations_and_d20_users}
        new_d20s = [
            UserEventD20Transaction(
                current_balance=d20s.current_balance - total_d20s,
                previous_balance=d20s.current_balance,
                delta=-total_d20s,
                event_id=event.id,
                user_id=user_id,
                previous_transaction_id=d20s.id,
                associated_time_slot_id=time_slot_id,
            )
            if user_id in existing_d20_map and (d20s := existing_d20_map[user_id]) is not None
            else UserEventD20Transaction(
                current_balance=-total_d20s,
                previous_balance=0,
                delta=-total_d20s,
                event_id=event.id,
                user_id=user_id,
                previous_transaction_id=None,
                associated_time_slot_id=time_slot_id,
            )
            for user_id, total_d20s in total_d20s_spent.items()
        ]

        transaction.add_all(new_d20s)

        # Already played
        new_user_game_playeds: list[dict[str, Any]] = []
        for result in results:
            party_members = party_member_mapping[result.party_leader_id[1]]
            for member_id in party_members:
                if result.session_id is None:
                    continue
                new_user_game_playeds.append(
                    {
                        "allow_play_again": False,
                        "user_id": member_id,
                        "game_id": session_game_id_map[result.session_id],
                    }
                )
        insert_user_game_played_stmt = (
            insert(UserGamePlayed)
            .values(new_user_game_playeds)
            .on_conflict_do_update(
                index_elements=(UserGamePlayed.user_id, UserGamePlayed.game_id),
                set_={
                    UserGamePlayed.allow_play_again: False,
                    UserGamePlayed.updated_at: dt.datetime.now(tz=dt.timezone.utc),
                    UserGamePlayed.updated_by: user_id_ctx.get(),
                },
            )
        )
        _ = await transaction.execute(insert_user_game_played_stmt)

        return "Compensated"
