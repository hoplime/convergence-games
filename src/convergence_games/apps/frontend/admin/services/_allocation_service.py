import datetime as dt
import itertools
from collections.abc import Sequence
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Any, TypedDict, cast

from litestar.exceptions import HTTPException
from pydantic import BaseModel
from rich.pretty import pprint
from sqlalchemy import bindparam, delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload, with_loader_criteria
from sqlalchemy.sql.selectable import Select, Subquery

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
from convergence_games.lib.ocean import Sqid, sink, swim
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

from .._common import PutEventManageAllocationSession


class TierAsDict(TypedDict):
    is_d20: bool
    tier: int


class AllocationPartyMetadata(BaseModel):
    gm_of: list[Sqid] = []
    tiers: dict[Sqid, TierAsDict] = {}


class AllocationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _party_leader_subquery(
        time_slot_id: int,
    ) -> tuple[Subquery, type[Party], type[PartyUserLink]]:
        # `aliased()` on a mapped class is annotated as `AliasedType[_O]` (== `Annotated[type[_O], "aliased"]`),
        # so the statically visible type of the aliases is `type[Party]` / `type[PartyUserLink]`, not `AliasedClass`.
        party_subq = (
            select(Party, PartyUserLink)
            .join(Party, Party.id == PartyUserLink.party_id, isouter=True)
            .where(Party.time_slot_id == time_slot_id)
            .subquery()
        )
        party_alias = aliased(Party, party_subq)
        party_user_link_alias = aliased(PartyUserLink, party_subq)
        return party_subq, party_alias, party_user_link_alias

    def resolve_time_slot(self, event: Event, time_slot_sqid: Sqid | None) -> TimeSlot:
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
        return time_slot

    async def committed_sessions_for_slot(self, time_slot_id: int) -> Sequence[Session]:
        sessions_stmt = (
            select(Session)
            .where(Session.time_slot_id == time_slot_id, Session.committed)
            .join(Table, Table.id == Session.table_id)
            .options(
                selectinload(Session.game),
                selectinload(Session.table),
            )
            .order_by(Table.name)
        )
        return (await self._session.execute(sessions_stmt)).scalars().all()

    async def allocation_groups(
        self, time_slot: TimeSlot, sessions: Sequence[Session]
    ) -> dict[int | None, list[tuple[User, Party | None, UserCheckinStatus | None, AllocationPartyMetadata]]]:
        sessions_by_gm_id: dict[int, list[Sqid]] = {}
        for session in sessions:
            sessions_by_gm_id.setdefault(session.game.gamemaster_id, []).append(swim(session))

        party_subq, party_alias, party_user_link_alias = self._party_leader_subquery(time_slot.id)

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
        groups = [r.tuple() for r in (await self._session.execute(solo_players_and_leaders_stmt)).all()]
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

        return group_dict

    async def compensation_applied(self, event_id: int, time_slot_id: int) -> bool:
        return (
            await self._session.execute(
                select(UserEventCompensationTransaction)
                .where(UserEventCompensationTransaction.event_id == event_id)
                .where(UserEventCompensationTransaction.associated_time_slot_id == time_slot_id)
                .limit(1)
            )
        ).scalar_one_or_none() is not None

    async def freeze_user_game_preferences(self, time_slot_id: int) -> None:
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
        _ = await self._session.execute(insert_user_game_preferences_update_stmt)

    async def run_allocation(self, time_slot_id: int) -> None:
        sessions, parties = await adapt_to_inputs(self._session, time_slot_id)
        game_allocator = GameAllocator(max_iterations=5000, debug_print=False)
        alg_results, compensation = game_allocator.allocate(sessions, parties, False)
        pprint(alg_results)
        pprint(compensation)
        await adapt_results_to_database(self._session, time_slot_id, alg_results, compensation)

    def set_time_slot_status(self, event: Event, time_slot_sqid: Sqid, status: TimeSlotStatus) -> TimeSlotStatus:
        time_slot_id = sink(time_slot_sqid)

        # Set the time slot status
        time_slot_id = sink(time_slot_sqid)
        time_slot = next(
            (ts for ts in event.time_slots if ts.id == time_slot_id),
            None,
        )

        if time_slot is None:
            raise HTTPException(status_code=404, detail="Time slot not found")

        time_slot.status = status

        self._session.add(time_slot)

        return status

    async def set_checkin(self, *, time_slot_id: int, user_id: int, checked_in: bool) -> None:
        checkin_status = (
            (
                await self._session.execute(
                    select(UserCheckinStatus).where(
                        UserCheckinStatus.user_id == user_id, UserCheckinStatus.time_slot_id == time_slot_id
                    )
                )
            )
            .scalars()
            .one_or_none()
        )

        if checkin_status is None:
            checkin_status = UserCheckinStatus(user_id=user_id, time_slot_id=time_slot_id, checked_in=checked_in)
        else:
            checkin_status.checked_in = checked_in

        self._session.add(checkin_status)

    async def replace_allocations(
        self, time_slot: TimeSlot, allocation_specs: Sequence[PutEventManageAllocationSession], *, commit: bool
    ) -> None:
        # Update the allocations to match the new data
        new_allocations: list[Allocation] = []

        for allocation_data in allocation_specs:
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

            if commit:
                # Also add a committed allocation for the party leader
                new_allocations.append(
                    Allocation(
                        party_leader_id=allocation_data.leader,
                        session_id=allocation_data.session,
                        committed=True,
                    )
                )

        time_slot.status = TimeSlotStatus.ALLOCATED if commit else TimeSlotStatus.ALLOCATING
        self._session.add(time_slot)

        # Remove existing allocations for this time slot
        delete_existing_allocations_stmt = delete(Allocation).where(Allocation.session.has(time_slot_id=time_slot.id))
        _ = await self._session.execute(delete_existing_allocations_stmt)

        # Add new allocations
        self._session.add_all(new_allocations)

    async def apply_compensation(self, event_id: int, time_slot_id: int) -> None:
        sessions, parties = await adapt_to_inputs(self._session, time_slot_id)
        parties = [AlgPartyP.from_alg_party(p) for p in parties]

        party_subq, party_alias, party_user_link_alias = self._party_leader_subquery(time_slot_id)
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
        allocations = [r.tuple() for r in (await self._session.execute(solo_players_and_leaders_stmt)).all()]
        gm_user_ids_this_session_stmt = (
            select(Session.id, Session.game_id, Game.gamemaster_id)
            .select_from(Session)
            .join(Game, (Session.time_slot_id == time_slot_id) & (Session.game_id == Game.id) & (Session.committed))
        )
        gm_user_ids_this_session = [
            r.tuple() for r in (await self._session.execute(gm_user_ids_this_session_stmt)).all()
        ]
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
        self._session.expunge_all()
        existing_compensations_and_d20_users = (
            (
                await self._session.execute(
                    select(User)
                    .where(User.id.in_(all_user_ids))
                    .options(
                        selectinload(User.latest_compensation_transaction),
                        selectinload(User.latest_d20_transaction),
                        with_loader_criteria(
                            UserEventCompensationTransaction,
                            UserEventCompensationTransaction.event_id == event_id,
                        ),
                        with_loader_criteria(
                            UserEventD20Transaction,
                            UserEventD20Transaction.event_id == event_id,
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
                event_id=event_id,
                user_id=user_id,
                previous_transaction_id=d20s.id,
                associated_time_slot_id=time_slot_id,
            )
            if user_id in existing_compensation_map and (d20s := existing_compensation_map[user_id]) is not None
            else UserEventCompensationTransaction(
                current_balance=total_compensation,
                previous_balance=0,
                delta=total_compensation,
                event_id=event_id,
                user_id=user_id,
                previous_transaction_id=None,
                associated_time_slot_id=time_slot_id,
            )
            # for party_leader_id, members in party_member_mapping.items()
            for user_id, total_compensation in total_compensations.items()
        ]

        self._session.add_all(new_compensations)

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
                event_id=event_id,
                user_id=user_id,
                previous_transaction_id=d20s.id,
                associated_time_slot_id=time_slot_id,
            )
            if user_id in existing_d20_map and (d20s := existing_d20_map[user_id]) is not None
            else UserEventD20Transaction(
                current_balance=-total_d20s,
                previous_balance=0,
                delta=-total_d20s,
                event_id=event_id,
                user_id=user_id,
                previous_transaction_id=None,
                associated_time_slot_id=time_slot_id,
            )
            for user_id, total_d20s in total_d20s_spent.items()
        ]

        self._session.add_all(new_d20s)

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
        _ = await self._session.execute(insert_user_game_played_stmt)


async def provide_allocation_service(transaction: AsyncSession) -> AllocationService:
    return AllocationService(transaction)
