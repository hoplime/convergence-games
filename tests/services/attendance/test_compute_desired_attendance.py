"""Unit tests for the pure ``compute_desired_attendance`` transformation.

Exercises the logic that turns committed Allocation rows + party_user_link
rows into a ``user_id -> DesiredAttendance`` map. Pure function -- no DB
required.
"""

from convergence_games.db.enums import AttendanceRole
from convergence_games.services.attendance import (
    AllocationRow,
    DesiredAttendance,
    PartyMemberRow,
    compute_desired_attendance,
)


def _alloc(allocation_id: int, leader_id: int, gm_id: int, game_id: int = 100, table_id: int = 200) -> AllocationRow:
    return AllocationRow(
        allocation_id=allocation_id,
        party_leader_id=leader_id,
        game_id=game_id,
        table_id=table_id,
        gamemaster_id=gm_id,
    )


def _party(party_id: int, user_id: int, is_leader: bool = False) -> PartyMemberRow:
    return PartyMemberRow(party_id=party_id, user_id=user_id, is_leader=is_leader)


def test_solo_leader_no_party_emits_one_player_row() -> None:
    # Leader 1 is not the GM (GM is user 99) and has no party -> they appear alone as PLAYER.
    desired = compute_desired_attendance(
        allocation_rows=[_alloc(allocation_id=10, leader_id=1, gm_id=99)],
        party_member_rows=[],
    )

    assert desired == {
        1: DesiredAttendance(game_id=100, role=AttendanceRole.PLAYER, table_id=200, source_allocation_id=10),
    }


def test_party_leader_expands_to_all_members_as_player() -> None:
    # Party 5 has leader 1 and members 2, 3.
    desired = compute_desired_attendance(
        allocation_rows=[_alloc(allocation_id=10, leader_id=1, gm_id=99)],
        party_member_rows=[
            _party(party_id=5, user_id=1, is_leader=True),
            _party(party_id=5, user_id=2),
            _party(party_id=5, user_id=3),
        ],
    )

    assert set(desired.keys()) == {1, 2, 3}
    for user_id in (1, 2, 3):
        assert desired[user_id].role is AttendanceRole.PLAYER
        assert desired[user_id].game_id == 100
        assert desired[user_id].source_allocation_id == 10


def test_gm_party_of_one_is_tagged_as_gamemaster() -> None:
    # Leader 7 is the GM of game 100 -> single GAMEMASTER row.
    desired = compute_desired_attendance(
        allocation_rows=[_alloc(allocation_id=11, leader_id=7, gm_id=7)],
        party_member_rows=[],
    )

    assert desired == {
        7: DesiredAttendance(game_id=100, role=AttendanceRole.GAMEMASTER, table_id=200, source_allocation_id=11),
    }


def test_mixed_gm_and_player_allocations() -> None:
    # Two allocations in the same slot: a player party and a separate GM party-of-one.
    desired = compute_desired_attendance(
        allocation_rows=[
            _alloc(allocation_id=10, leader_id=1, gm_id=7, game_id=100, table_id=200),
            _alloc(allocation_id=11, leader_id=7, gm_id=7, game_id=100, table_id=200),
        ],
        party_member_rows=[
            _party(party_id=5, user_id=1, is_leader=True),
            _party(party_id=5, user_id=2),
        ],
    )

    assert desired[1].role is AttendanceRole.PLAYER
    assert desired[2].role is AttendanceRole.PLAYER
    assert desired[7].role is AttendanceRole.GAMEMASTER


def test_empty_inputs_produce_empty_desired() -> None:
    assert compute_desired_attendance(allocation_rows=[], party_member_rows=[]) == {}


def test_party_without_leader_falls_back_to_solo_leader_user_id() -> None:
    # Pathological: party_user_link has the leader as a non-leader row, so we
    # treat them as a solo party and emit just the leader.
    desired = compute_desired_attendance(
        allocation_rows=[_alloc(allocation_id=10, leader_id=1, gm_id=99)],
        party_member_rows=[
            _party(party_id=5, user_id=1, is_leader=False),
            _party(party_id=5, user_id=2, is_leader=False),
        ],
    )

    assert set(desired.keys()) == {1}
    assert desired[1].role is AttendanceRole.PLAYER
