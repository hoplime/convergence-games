from dataclasses import dataclass, field

from convergence_games.db.enums import UserGamePreferenceValue as UGPV

type SessionID = int
type PartyID = int


@dataclass
class AlgParty:
    party_id: PartyID
    group_size: int
    preferences: list[tuple[SessionID, UGPV]]
    total_compensation: int


@dataclass
class AlgSession:
    session_id: SessionID
    min_players: int
    opt_players: int
    max_players: int
    compensation: int  # GM's compensation
    tags: list[str] = field(default_factory=list)


@dataclass
class AlgResult:
    party_id: PartyID
    session_id: SessionID | None
