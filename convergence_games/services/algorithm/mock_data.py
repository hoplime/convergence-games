from dataclasses import dataclass, field
from random import Random
from typing import Protocol, override

from convergence_games.db.enums import UserGamePreferenceValue as UGPV
from convergence_games.services.algorithm.models import AlgParty, AlgSession, PartyID, SessionID


@dataclass
class MockDataState:
    parties: list[AlgParty] = field(default_factory=list)
    sessions: list[AlgSession] = field(default_factory=list)


class SessionGenerator(Protocol):
    def __call__(self, r: Random, state: MockDataState, session_id: SessionID) -> AlgSession: ...


class PartyGenerator(Protocol):
    def __call__(self, r: Random, state: MockDataState, party_id: PartyID) -> AlgParty: ...


class MockDataGenerator:
    def __init__(
        self,
        session_generator: SessionGenerator,
        party_generator: PartyGenerator,
        seed: int = 42,
    ) -> None:
        self.r: Random = Random(seed)
        self._state: MockDataState = MockDataState()
        self.session_generator: SessionGenerator = session_generator
        self.party_generator: PartyGenerator = party_generator

    def refresh_state(self):
        self._state = MockDataState()

    def create_scenario(
        self,
        session_count: int,
        party_count: int,
    ) -> tuple[list[AlgSession], list[AlgParty]]:
        for session_id in range(session_count):
            session = self.session_generator(self.r, self._state, session_id)
            self._state.sessions.append(session)

        for party_id in range(party_count):
            party = self.party_generator(self.r, self._state, party_id)
            self._state.parties.append(party)

        return self._state.sessions, self._state.parties


class DefaultSessionGenerator(SessionGenerator):
    @override
    def __call__(self, r: Random, state: MockDataState, session_id: SessionID) -> AlgSession:
        game_type = "MULTITABLE" if session_id % 20 == 0 else "REGULAR"
        match game_type:
            case "REGULAR":
                player_counts = sorted(r.sample(range(3, 6), 3))
            case "MULTITABLE":
                player_counts = sorted(r.sample(range(12, 26), 3))
        return AlgSession(
            session_id=session_id,
            min_players=player_counts[0],
            opt_players=player_counts[1],
            max_players=player_counts[2],
            compensation=r.choice([0] * 20 + [10, 20, 30]),
            tags=[game_type],
        )


class DefaultPartyGenerator(PartyGenerator):
    @override
    def __call__(self, r: Random, state: MockDataState, party_id: PartyID) -> AlgParty:
        def preference_generator(has_d20: bool, session: AlgSession) -> UGPV:
            choices = [UGPV.D0] * 5 + [UGPV.D4, UGPV.D6, UGPV.D8, UGPV.D10, UGPV.D12]
            if has_d20:
                choices.append(UGPV.D20)
            if "MULTITABLE" in session.tags:
                if has_d20:
                    choices.extend([UGPV.D20] * 3)
                else:
                    choices.extend([UGPV.D12] * 3)
            return r.choice(choices)

        group_size = r.choice([1] * 10 + [2, 3])
        party = AlgParty(
            party_id=party_id,
            group_size=group_size,
            preferences=[
                (
                    session.session_id,
                    preference_generator(
                        r.choice([False] * 4 + [True]),
                        session,
                    ),
                )
                for session in state.sessions
            ],
            total_compensation=sum(r.choice([0] * 20 + [1, 2, 3]) for _ in range(group_size)),
        )

        # If the party has fewer than 2 sessions without a D0, mark up to 2 as randomly D12/D10
        if sum(1 for _, pref in party.preferences if pref != UGPV.D0) < 2:
            random_indices = r.sample(range(len(party.preferences)), k=2)
            for i in random_indices:
                party.preferences[i] = (party.preferences[i][0], r.choice([UGPV.D10, UGPV.D12]))

        return party
