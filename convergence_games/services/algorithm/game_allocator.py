from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from functools import total_ordering
from itertools import groupby
from operator import itemgetter
from random import Random
from typing import Literal, Self, cast, final, override

from rich import print
from rich.pretty import pprint

from convergence_games.db.enums import UserGamePreferenceValue as UGPV
from convergence_games.services.algorithm.models import AlgParty, AlgResult, AlgSession, PartyID, SessionID


# This is used to sort the tiers, so that D20 is always first, then D12, etc.
# LOWER = STRONGER PREFERENCE = EARLIER SORT ORDER = BETTER NUMBER ON THE TIER
@total_ordering
@dataclass(frozen=True)
class Tier:
    is_d20: bool
    tier: int
    # 0,  - e.g. D20 or FIRST CHOICE
    # 1,  - e.g. D12 or SECOND CHOICE
    # 2,  - e.g. D8  or THIRD CHOICE
    # 3,  - e.g. D6  ...
    # 4,  - e.g. D4  ...
    # 5,  - e.g. D0  - Impossible, we don't even include in the tier list

    @classmethod
    def zero(cls) -> Self:
        return cls(is_d20=False, tier=5)

    @override
    def __repr__(self) -> str:
        return "D20" if self.is_d20 else f"T{self.tier}"

    def __lt__(self, other: Self) -> bool:
        if self.is_d20 and not other.is_d20:
            return True
        if not self.is_d20 and other.is_d20:
            return False
        return self.tier < other.tier

    def beats(self, other: Self) -> bool:
        return self < other


@dataclass
class AlgPartyP:
    party_id: PartyID
    group_size: int
    compensation: int
    tier_list: list[tuple[Tier, list[SessionID]]]
    tier_by_session: dict[SessionID, Tier]

    @property
    def has_d20(self) -> bool:
        return self.tier_list[0][0].is_d20 if self.tier_list else False

    @classmethod
    def from_alg_party(cls, party: AlgParty) -> Self:
        tier_list = cls._init_tier_list(party.preferences)
        return cls(
            party_id=party.party_id,
            group_size=party.group_size,
            compensation=party.total_compensation,
            tier_list=tier_list,
            tier_by_session={session_id: tier for tier, session_ids in tier_list for session_id in session_ids},
        )

    @staticmethod
    def _init_tier_list(preferences: list[tuple[SessionID, UGPV]]) -> list[tuple[Tier, list[SessionID]]]:
        # Order down from D20 to D0
        ordered_preferences = sorted([p for p in preferences if p[1] != UGPV.D0], key=itemgetter(1), reverse=True)
        tier_list: list[tuple[Tier, list[SessionID]]] = []
        for i, (preference, group) in enumerate(groupby(ordered_preferences, key=itemgetter(1))):
            preference: UGPV
            tier_list.append((Tier(is_d20=preference == UGPV.D20, tier=i), [session_id for session_id, _ in group]))
        return tier_list


@dataclass
class CurrentAllocation:
    session: AlgSession
    parties: list[AlgPartyP] = field(default_factory=list)

    @property
    def player_count(self) -> int:
        return sum(party.group_size for party in self.parties)

    @property
    def players_to_max(self) -> int:
        return self.session.max_players - self.player_count

    @property
    def players_to_opt(self) -> int:
        return self.session.opt_players - self.player_count

    @property
    def players_to_min(self) -> int:
        return self.session.min_players - self.player_count


type SessionSearchPriorityMode = Literal[
    "RANDOM", "BY_LEAST_POPULAR", "BY_PLAYERS_TO_MIN", "BY_PLAYERS_TO_OPT", "BY_PLAYERS_TO_MAX", "IN_ORDER"
]
type SessionCanFitMode = Literal["MIN", "OPT", "MAX"]


@final
class GameAllocator:
    def __init__(self, max_iterations: int = 1) -> None:
        self.r = Random()
        self._max_iterations = max_iterations

    def _single_allocate(self, sessions: list[AlgSession], parties: list[AlgPartyP]) -> list[AlgResult]:
        # Process:
        # 1. Allocate D20 Players - They MUST, if possible, go to one of their D20 games at all costs
        # 2. Look for the least popular games judged by how many people have them as first choice
        #   - these will be limited, so we need an initial attempt to place first choices in there
        #   - seed them with first choices IF POSSIBLE
        # 3. Fill the other games to minimum as well as possible
        # 4. Assign remaining players based on their preferences
        # 5. For any games still under minimum, see if we can accept side-grades (or single tier downs?)
        # 6. For any game STILL under minimum, allocate their GM

        # This holds the whole working state and has internal allocation functions

        # State
        # TODO: Maybe cache the lookups
        party_lookup = {party.party_id: party for party in parties}
        session_lookup = {session.session_id: session for session in sessions}
        free_party_ids: set[PartyID] = {party.party_id for party in parties}
        current_allocations: dict[SessionID, CurrentAllocation] = {
            session.session_id: CurrentAllocation(session=session) for session in sessions
        }
        # TODO: Do we need to store if a party has been bumped down? We really shouldn't be bumping a group down
        # more than 1 tier from an original placement to accomodate player spread

        # Functions
        def shuffled[T](l: list[T]) -> list[T]:
            self.r.shuffle(l)
            return l

        def sorted_sessions(
            sessions: list[SessionID],
            mode: SessionSearchPriorityMode = "RANDOM",
        ) -> list[SessionID]:
            if mode == "RANDOM":
                return self.r.sample(sessions, len(sessions))
            elif mode in ("BY_LEAST_POPULAR", "BY_LEAST_PLAYERS_TO_MIN", "BY_LEAST_PLAYERS_TO_OPTIMAL"):
                # TODO: Implement other sorting strategies here
                return sessions
            elif mode == "IN_ORDER":
                return sessions
            return sessions

        def allocate_party(
            party: AlgPartyP,
            min_acceptable_tier: Tier | None = None,
            session_priority_mode: SessionSearchPriorityMode = "RANDOM",
            can_fit_mode: SessionCanFitMode = "MAX",
            allow_bump: bool = False,
            max_bump_tier_down: int = 0,
            blocked_session_ids: set[SessionID] | None = None,
        ) -> SessionID | None:
            if blocked_session_ids is None:
                blocked_session_ids = set()

            def _() -> SessionID | None:
                # Iterate in descending order of tier
                for tier, session_ids in party.tier_list:
                    if min_acceptable_tier is not None and min_acceptable_tier.beats(tier):
                        return

                    # Pass 1 - Allocate to the first table that fits within this tier
                    for session_id in sorted_sessions(session_ids, mode=session_priority_mode):
                        if session_id in blocked_session_ids:
                            continue

                        current_allocation = current_allocations[session_id]
                        if party.group_size <= (
                            current_allocation.players_to_min
                            if can_fit_mode == "MIN"
                            else current_allocation.players_to_opt
                            if can_fit_mode == "OPT"
                            else current_allocation.players_to_max
                        ):
                            return session_id

                    if not allow_bump:
                        continue

                    # Pass 2 - Allow Bumping
                    for session_id in sorted_sessions(session_ids, mode=session_priority_mode):
                        if session_id in blocked_session_ids:
                            continue

                        current_allocation = current_allocations[session_id]
                        for other_party in current_allocation.parties:
                            could_fit_if_swapped = party.group_size - other_party.group_size <= (
                                current_allocation.players_to_min
                                if can_fit_mode == "MIN"
                                else current_allocation.players_to_opt
                                if can_fit_mode == "OPT"
                                else current_allocation.players_to_max
                            )
                            if not could_fit_if_swapped:
                                continue
                            print(f"Trying to bump {other_party.party_id} from {session_id}")
                            tier_of_other_party_currently = other_party.tier_by_session.get(session_id, Tier.zero())
                            if allocate_party(
                                other_party,
                                min_acceptable_tier=Tier(
                                    is_d20=tier_of_other_party_currently.is_d20,
                                    tier=tier_of_other_party_currently.tier + max_bump_tier_down,
                                ),
                                session_priority_mode=session_priority_mode,
                                can_fit_mode=can_fit_mode,
                                allow_bump=False,
                                blocked_session_ids={session_id},
                            ):
                                # We successfully moved the other party, so REMOVE THEM FROM HERE and slot us in
                                current_allocations[session_id].parties.remove(other_party)
                                return session_id

            result_session_id = _()

            if result_session_id is not None:
                if party.party_id in free_party_ids:
                    free_party_ids.remove(party.party_id)
                current_allocations[result_session_id].parties.append(party)

            return result_session_id

        def try_to_fill_session(session_id: SessionID) -> bool:
            current_allocation = current_allocations[session_id]
            number_of_players_required_min = current_allocation.players_to_min
            number_of_players_required_max = current_allocation.players_to_max
            # Only the sessions above optimum
            valid_sessions_to_poach_from = [
                other_session_id
                for other_session_id, other_allocation in current_allocations.items()
                if other_session_id != session_id and other_allocation.players_to_opt < 0
            ]

            # Get all the possible parties
            candidate_parties: list[tuple[SessionID, PartyID]] = []
            valid_parties_to_poach = [
                party
                for other_session_id in valid_sessions_to_poach_from
                for party in current_allocations[other_session_id].parties
                if (
                    # 1. Can't take too many players into the session we're trying to fill
                    party.group_size <= number_of_players_required_max
                    # 3. Can't take too many player FROM the session we're poaching from
                    # So the players OVER min = -players_to_min
                    # If we take away the group size from the player count, players OVER min drops by the group size
                    # So players_over_min_new = -players_to_min + group_size
                    # e.g. a session is at 6 players, min is 4
                    #     players_to_min = -2
                    # if we remove a group of size 3, that session ends up at 3 players
                    #     players_to_min = 1
                    # this result actually needs to be <= 0, so we can take maximum 2
                    # i.e the group_size <= players_over_min
                    and party.group_size <= -current_allocations[other_session_id].players_to_min
                )
            ]
            return False

        # Do it
        # Step 1 - Allocate parties using a D20
        # Allow filling to max
        # Don't allow anything below tier 0
        print("Step 1 | Allocating D20s")
        for party in shuffled([party for party in parties if party.has_d20]):
            session_id = allocate_party(
                party,
                min_acceptable_tier=Tier(is_d20=True, tier=0),
                session_priority_mode="RANDOM",
                can_fit_mode="MAX",
                allow_bump=True,
            )
            print(f"Party {party.party_id} allocated to session {session_id}")

        # Step 2 - Allocate remaining parties
        # Preferring least popular games to give them a chance
        # Allow filling to the minimum
        # Don't allow anything below tier 1
        print("Step 2 | Allocating Remaining Parties - Minimum")
        for party in shuffled([party_lookup[party_id] for party_id in free_party_ids]):
            session_id = allocate_party(
                party,
                min_acceptable_tier=Tier(is_d20=False, tier=1),
                session_priority_mode="BY_LEAST_POPULAR",
                can_fit_mode="MIN",
                allow_bump=True,
            )
            print(f"Party {party.party_id} allocated to session {session_id}")

        # Step 3 - Allocate remaining parties
        # By random
        # Allow filling to the optimum
        # Don't allow anything below tier 1
        print("Step 3 | Allocating Remaining Parties - Optimum Pass")
        for party in shuffled([party_lookup[party_id] for party_id in free_party_ids]):
            session_id = allocate_party(
                party,
                min_acceptable_tier=Tier(is_d20=False, tier=1),
                session_priority_mode="RANDOM",
                can_fit_mode="OPT",
                allow_bump=True,
            )
            print(f"Party {party.party_id} allocated to session {session_id}")

        # Step 4 - We still have remaining parties
        # By least players to optimum
        # Allow filling to the maximum
        # Allow any tier
        print("Step 4 | Allocating Remaining Parties - Final Pass")
        for party in shuffled([party_lookup[party_id] for party_id in free_party_ids]):
            session_id = allocate_party(
                party,
                min_acceptable_tier=None,
                session_priority_mode="RANDOM",
                can_fit_mode="MAX",
                allow_bump=True,
            )
            print(f"Party {party.party_id} allocated to session {session_id}")

        # Step 5 - Now, there's gonna be games that don't have minimum players
        # Let's try to fill them up by taking from tables which are over the optimum
        # And have a group with a preference that wouldn't be downgraded more than once
        unfillable_session_ids: set[SessionID] = set()
        print("Step 5 | Trying to Fill Tables Below Minimum")
        unfilled_session_ids = [
            session_id
            for session_id, current_allocation in current_allocations.items()
            if current_allocation.players_to_min > 0
        ]
        for session_id in shuffled(unfilled_session_ids):
            if try_to_fill_session(session_id):
                print(f"Filled session {session_id}")
            else:
                print(f"Failed to fill session {session_id}")
                unfillable_session_ids.add(session_id)

        # Step 6 - It is not possible to get enough players into this game
        # We need to allocate the GM and any remaining parties to other games
        print("Step 6 | Allocating GM and Remaining Parties From Unfillable Games")
        for session_id in shuffled(list(unfillable_session_ids)):
            pass

        return [
            AlgResult(party_id=party_id, session_id=session_id)
            for session_id, current_allocation in current_allocations.items()
            for party_id in (party.party_id for party in current_allocation.parties)
        ]

    def _allocate(self, sessions: list[AlgSession], parties: list[AlgPartyP]) -> tuple[list[AlgResult], Compensation]:
        print("Allocating for:")
        pprint(sessions)
        pprint(parties)
        best_results: list[AlgResult] | None = None
        best_compensation: Compensation | None = None
        for i in range(self._max_iterations):
            print(f"Iteration {i + 1} of {self._max_iterations}")
            results = self._single_allocate(sessions, parties)
            valid = is_valid_allocation(sessions, parties, results)
            compensation = calculate_compensation(sessions, parties, results)
            pprint(results)
            print(f"Valid = {valid}")
            pprint(compensation)
            print(f"Compensation Total = {compensation.total}")
            if best_compensation is None or compensation < best_compensation:
                print("Better result :white_check_mark:")
                best_results = results
                best_compensation = compensation
            print("")

        if best_results is None or best_compensation is None:
            raise ValueError("No valid allocation found")

        return best_results, best_compensation

    def allocate(self, sessions: list[AlgSession], parties: list[AlgParty]) -> tuple[list[AlgResult], Compensation]:
        return self._allocate(
            sessions,
            [AlgPartyP.from_alg_party(party=party) for party in parties],
        )


@total_ordering
@dataclass(eq=False)
class Compensation:
    party_compensations: dict[PartyID, int]
    session_compensations: dict[SessionID, int]
    session_virtual_compensations: dict[SessionID, int]

    @property
    def real_total(self) -> int:
        return sum(self.party_compensations.values()) + sum(self.session_compensations.values())

    @property
    def total(self) -> int:
        return (
            sum(self.party_compensations.values())
            + sum(self.session_compensations.values())
            + sum(self.session_virtual_compensations.values())
        )

    @override
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Compensation):
            return NotImplemented
        return self.real_total == other.real_total and self.total == other.total

    def __lt__(self, other: Self) -> bool:
        return self.total < other.total


def calculate_compensation(
    sessions: list[AlgSession], parties: list[AlgPartyP], results: list[AlgResult]
) -> Compensation:
    # Sum up "compensation" - a value which represents how much each party and GM has _missed out_ on getting what they want
    # Lower is better!

    # As a party:
    # - You reset current compensation of all members to 0 if you get into a tier 0 game
    #   (i.e. a negative compensation for this allocation of the party's total compensation)
    # - Otherwise, you grant compensation to all members based on the game's tier
    #   (i.e. a positive compensation for the allocation of group_size * the game's tier)

    # As a session runner (GM):
    # - You reset current compensation to 0 if you get the optimal player count
    #   (i.e. a negative compensation for this allocation of the GM's total compensation)
    # - If the game runs, but not at optimal player count, you get 1 VIRTUAL compensation for each difference in player count
    # - If the game doesn't run at all, you grant compensation to the GM as follows:
    #   10 points
    #   and then double (?) the total points if the GM already had some compensation

    # 0. Data structures
    party_lookup = {party.party_id: party for party in parties}
    session_lookup = {session.session_id: session for session in sessions}
    party_compensations = {party.party_id: 0 for party in parties}
    session_compensations = {session.session_id: 0 for session in sessions}
    session_virtual_compensations = {session.session_id: 0 for session in sessions}

    # 1. Calculate party compensations
    for result in results:
        result_tier = (
            party_lookup[result.party_id].tier_by_session.get(result.session_id, Tier.zero())
            if result.session_id is not None
            else Tier.zero()
        )
        if result_tier.tier == 0:
            # Got first choice - reset compensation
            party_compensations[result.party_id] = -party_lookup[result.party_id].compensation
        else:
            # Didn't get first choice - grant compensation based on tier
            party_compensations[result.party_id] += party_lookup[result.party_id].group_size * result_tier.tier

    # 2a. Player counts
    result_player_counts = {session.session_id: 0 for session in sessions}
    opt_player_counts = {session.session_id: session.opt_players for session in sessions}
    for result in results:
        if result.session_id is not None:
            result_player_counts[result.session_id] += party_lookup[result.party_id].group_size

    # 2b. GM compensation
    for session_id, result_count in result_player_counts.items():
        session = session_lookup[session_id]
        if result_count == opt_player_counts[session_id]:
            # Got optimal player count - reset compensation
            session_compensations[session_id] = -session.compensation
        elif result_count == 0:
            # Session didn't run at all, grant compensation to GM
            if session:
                already_had_compensation = session.compensation > 0
                session_compensations[session_id] += 10
                if already_had_compensation:
                    session_compensations[session_id] *= 2
        else:
            # Session ran, but not at optimal player count, grant virtual compensation
            difference = abs(result_count - opt_player_counts[session_id])
            session_virtual_compensations[session_id] += difference

    return Compensation(
        party_compensations=party_compensations,
        session_compensations=session_compensations,
        session_virtual_compensations=session_virtual_compensations,
    )


def is_valid_allocation(sessions: list[AlgSession], parties: list[AlgPartyP], results: list[AlgResult]) -> bool:
    success = True

    # 0. Data structures
    party_lookup = {party.party_id: party for party in parties}

    # 1. Every party must be allocated to exactly one session (None is a valid session ID, with no max)
    party_id_count = Counter([party.party_id for party in parties])
    result_id_count = Counter([result.party_id for result in results])
    diff = party_id_count - result_id_count
    if diff:
        print("Not all parties are allocated, or excess are allocated")
        print(diff)
        success = False

    # 2. No session may be below the min_players or above the max_players IF it has any players
    result_player_counts = {session.session_id: 0 for session in sessions}
    min_player_counts = {session.session_id: session.min_players for session in sessions}
    max_player_counts = {session.session_id: session.max_players for session in sessions}
    for result in results:
        if result.session_id is not None:
            result_player_counts[result.session_id] += party_lookup[result.party_id].group_size

    for session_id, result_count in result_player_counts.items():
        if result_count == 0:
            continue
        if result_count < min_player_counts[session_id]:
            print(f"Session {session_id} has too few players: {result_count} < {min_player_counts[session_id]}")
            success = False
        if result_count > max_player_counts[session_id]:
            print(f"Session {session_id} has too many players: {result_count} > {max_player_counts[session_id]}")
            success = False

    return success


if __name__ == "__main__":
    import argparse

    from convergence_games.services.algorithm.mock_data import (
        DefaultPartyGenerator,
        DefaultSessionGenerator,
        MockDataGenerator,
    )

    # End to End
    parser = argparse.ArgumentParser()
    _ = parser.add_argument("--sessions", "-s", type=int, default=3)
    _ = parser.add_argument("--parties", "-p", type=int, default=16)
    _ = parser.add_argument("--iterations", "-i", type=int, default=1)
    args = parser.parse_args()

    mock_data_generator = MockDataGenerator(
        session_generator=DefaultSessionGenerator(), party_generator=DefaultPartyGenerator()
    )
    sessions, parties = mock_data_generator.create_scenario(
        session_count=cast(int, args.sessions),
        party_count=cast(int, args.parties),
    )
    game_allocator = GameAllocator(max_iterations=cast(int, args.iterations))
    results, compensation = game_allocator.allocate(sessions, parties)
    print("Final Results:")
    pprint(results)
    print("Final Compensation:")
    pprint(compensation)
    print(compensation.total)
    print(compensation.real_total)
