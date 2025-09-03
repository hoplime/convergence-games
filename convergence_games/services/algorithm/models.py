from dataclasses import dataclass, field
from typing import Literal

from convergence_games.db.enums import UserGamePreferenceValue as UGPV

# Typing with lists of things is _weird_
# so SessionID of "OVERFLOW" is the only valid string value - but we don't use Literal["OVERFLOW"] because of invariance
type SessionID = int | str

type PartyID = tuple[Literal["PARTY", "USER", "GM", "OVERFLOW"], int]


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
    gm_party: AlgParty
    tags: list[str] = field(default_factory=list)


@dataclass
class AlgResult:
    party_id: PartyID
    session_id: SessionID | None
