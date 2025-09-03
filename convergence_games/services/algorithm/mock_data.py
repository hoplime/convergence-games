from random import Random
from typing import cast, final, override

from convergence_games.db.enums import UserGamePreferenceValue as UGPV
from convergence_games.services.algorithm.models import AlgParty, AlgSession, PartyLeaderID, SessionID


@final
class MockDataGenerator:
    def __init__(
        self, session_count: int, party_count: int, seed: int = 42, multitable_ids: list[SessionID] | None = None
    ) -> None:
        self.r: Random = Random(seed)
        if multitable_ids is None:
            multitable_ids = []
        self._multitable_ids: list[SessionID] = multitable_ids
        self._session_ids = range(session_count)
        self._party_ids = cast(list[PartyLeaderID], [("USER", i) for i in range(party_count)])

    def _generate_session(self, session_id: SessionID) -> AlgSession:
        game_type = "MULTITABLE" if session_id in self._multitable_ids else "REGULAR"
        match game_type:
            case "REGULAR":
                player_counts = sorted([self.r.randint(2, 8) for _ in range(3)])
            case "MULTITABLE":
                player_counts = sorted([self.r.randint(12, 25) for _ in range(3)])
        return AlgSession(
            session_id=session_id,
            min_players=player_counts[0],
            opt_players=player_counts[1],
            max_players=player_counts[2],
            compensation=self.r.choice([0] * 20 + [10, 20, 30]),
            tags=[game_type],
            gm_party=self._generate_party(
                ("GM", cast(int, session_id)),
                force_group_size=1,
            ),
        )

    def _generate_party(self, party_id: PartyLeaderID, force_group_size: int | None = None) -> AlgParty:
        def preference_generator(has_d20: bool, session_id: SessionID) -> UGPV:
            choices = [UGPV.D0] * 5 + [UGPV.D4, UGPV.D6, UGPV.D8, UGPV.D10, UGPV.D12]
            if has_d20:
                choices.append(UGPV.D20)
            # Multitables are popular!
            if session_id in self._multitable_ids:
                if has_d20:
                    choices.extend([UGPV.D20] * 6)
                else:
                    choices.extend([UGPV.D12] * 6)
            return self.r.choice(choices)

        group_size = force_group_size if force_group_size is not None else self.r.choice([1] * 10 + [2, 3])
        if group_size > 1:
            party_id = ("USER", party_id[1])
        party = AlgParty(
            party_leader_id=party_id,
            group_size=group_size,
            preferences=[
                (
                    session_id,
                    preference_generator(
                        self.r.choice([False] * 4 + [True]),
                        session_id,
                    ),
                )
                for session_id in self._session_ids
            ],
            total_compensation=sum(self.r.choice([0] * 20 + [1, 2, 3]) for _ in range(group_size)),
        )

        # If the party has fewer than 2 sessions without a D0, mark up to 2 as randomly D12/D10
        if sum(1 for _, pref in party.preferences if pref != UGPV.D0) < 2:
            random_indices = self.r.sample(range(len(party.preferences)), k=2)
            for i in random_indices:
                party.preferences[i] = (party.preferences[i][0], self.r.choice([UGPV.D10, UGPV.D12]))

        return party

    def run(
        self,
    ) -> tuple[list[AlgSession], list[AlgParty]]:
        sessions = [self._generate_session(session_id) for session_id in self._session_ids]
        parties = [self._generate_party(party_id) for party_id in self._party_ids]
        return sessions, parties
