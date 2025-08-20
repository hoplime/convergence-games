from collections import Counter
from dataclasses import dataclass
from functools import total_ordering
from itertools import groupby
from operator import itemgetter
from random import Random
from typing import Literal, Self, final, override

from rich.pretty import pprint

from convergence_games.db.enums import UserGamePreferenceValue as UGPV
from convergence_games.services.algorithm.mock_data import (
    DefaultPartyGenerator,
    DefaultSessionGenerator,
    MockDataGenerator,
    MockDataState,
)
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


@final
class GameAllocator:
    def __init__(self) -> None:
        self.r = Random()

    def _allocate(self, sessions: list[AlgSession], parties: list[AlgPartyP]) -> list[AlgResult]:
        pprint(sessions)
        pprint(parties)
        return []

    def allocate(self, sessions: list[AlgSession], parties: list[AlgParty]) -> list[AlgResult]:
        return self._allocate(
            sessions,
            [AlgPartyP.from_alg_party(party=party) for party in parties],
        )


def compensation_value(sessions: list[AlgSession], parties: list[AlgPartyP], results: list[AlgResult]) -> int:
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

    return (
        sum(session_compensations.values())
        + sum(session_virtual_compensations.values())
        + sum(party_compensations.values())
    )


def is_valid_allocation(sessions: list[AlgSession], parties: list[AlgParty], results: list[AlgResult]) -> bool:
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
