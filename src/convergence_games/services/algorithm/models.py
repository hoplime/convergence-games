from dataclasses import dataclass, field
from typing import Literal

from convergence_games.db.enums import UserGamePreferenceValue

type SessionID = int

type PartyLeaderID = tuple[Literal["USER", "GM", "OVERFLOW"], int]


@dataclass
class AlgParty:
    party_leader_id: PartyLeaderID
    group_size: int
    preferences: list[tuple[SessionID, tuple[UserGamePreferenceValue, bool]]]  # (preference, already_played)
    total_compensation: int


@dataclass
class AlgSession:
    session_id: SessionID | None
    min_players: int
    opt_players: int
    max_players: int
    compensation: int  # GM's compensation
    gm_party: AlgParty
    tags: list[str] = field(default_factory=list)


@dataclass
class AlgResult:
    party_leader_id: PartyLeaderID
    session_id: SessionID | None
    assignment_type: Literal["PLAYER", "GM"]
