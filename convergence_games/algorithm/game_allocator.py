import argparse
import enum
import itertools
import random
import shutil
from collections import defaultdict
from dataclasses import dataclass, field
from functools import total_ordering
from itertools import groupby
from pathlib import Path
from pprint import pprint
from typing import Any, Literal, Self, TypeAlias

import polars as pl
from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, col, create_engine, func, select

from convergence_games.db.base_data import ALL_BASE_DATA
from convergence_games.db.extra_types import GroupHostingMode
from convergence_games.db.models import (
    Game,
    Person,
    PersonSessionSettings,
    PersonSessionSettingsWithExtra,
    PersonWithExtra,
    SessionPreference,
    TableAllocation,
    TableAllocationWithExtra,
    TimeSlot,
)
from convergence_games.db.sheets_importer import GoogleSheetsImporter


# region Database initialization
def create_mock_engine(force_recreate: bool = False) -> Engine:
    mock_base_path = Path("mock_base.db")
    if force_recreate and mock_base_path.exists():
        mock_base_path.unlink()

    if not mock_base_path.exists():
        mock_base_engine = create_engine(f"sqlite:///{str(mock_base_path)}")
        SQLModel.metadata.create_all(mock_base_engine)

        imported_dbos = GoogleSheetsImporter.from_urls().import_all()
        with Session(mock_base_engine) as session:
            session.add_all(ALL_BASE_DATA)
            session.add_all(imported_dbos)
            session.commit()

    mock_runtime_path = Path("mock_runtime.db")
    if mock_runtime_path.exists():
        mock_runtime_path.unlink()
    shutil.copy(mock_base_path, mock_runtime_path)
    mock_runtime_engine = create_engine(f"sqlite:///{str(mock_runtime_path)}")
    SQLModel.metadata.create_all(mock_runtime_engine)

    return mock_runtime_engine


def create_simulated_player_data(args: argparse.Namespace) -> None:
    random.seed(42)

    mock_runtime_engine = create_mock_engine(force_recreate=args.force_recreate)

    with Session(mock_runtime_engine) as session:
        # SIMULATE NEW PLAYERS
        current_n_players: int = session.exec(func.count(Person.id)).scalar()

        simulated_persons = [
            Person(
                name=f"Simulated {i:03d}",
                email=f"simulated{i:03d}@email.com",
            )
            for i in range(current_n_players + 1, args.n_players + 1)
        ]

        session.add_all(simulated_persons)
        session.commit()

        # GET ALL TABLE ALLOCATIONS
        persons = session.exec(select(Person)).all()
        table_allocations = session.exec(select(TableAllocation)).all()
        time_slots = session.exec(select(TimeSlot)).all()

        # SIMULATE GOLDEN D20s
        people_with_golden_d20 = random.sample(persons, args.n_with_golden_d20)
        for person in people_with_golden_d20:
            person.golden_d20s = 1
        session.add_all(people_with_golden_d20)

        # SIMULATE SESSION PREFERENCES
        for person in persons:
            for table_allocation in table_allocations:
                possible_options = [0, 1, 2, 3, 4, 5, 20] if person.golden_d20s > 0 else [0, 1, 2, 3, 4, 5]
                session_preference = SessionPreference(
                    preference=random.choice(possible_options),  # TODO: Weighted preferences
                    person_id=person.id,
                    table_allocation_id=table_allocation.id,
                )
                # We also simulate _not_ having a preference for a table allocation sometimes if it's a 3 - i.e. the default
                if session_preference.preference == 3 and random.random() < 0.5:
                    continue
                session.add(session_preference)

        # SIMULATE PERSON SESSION SETTINGS
        for person in persons:
            for time_slot in time_slots:
                session.add(PersonSessionSettings(person_id=person.id, time_slot_id=time_slot.id, checked_in=True))

        # SIMULATE GROUPS
        for time_slot in time_slots:
            print("Time Slot:", time_slot)
            players_gming_this_session = session.exec(
                select(Person)
                .join(Game, Game.gamemaster_id == Person.id)
                .join(TableAllocation, TableAllocation.game_id == Game.id)
                .join(TimeSlot, TimeSlot.id == TableAllocation.time_slot_id)
                .filter(TimeSlot.id == time_slot.id)
            ).all()
            # print("GMing", len(players_gming_this_session))
            # Exclude GMs from the list of players to group
            players_eligible_to_group = [person for person in persons if person not in players_gming_this_session]
            # print("GROUPABLE", len(players_eligible_to_group))
            for group_size, n_groups in [(2, args.n_groups_of_2), (3, args.n_groups_of_3)]:
                for _ in range(n_groups):
                    group = random.sample(players_eligible_to_group, group_size)
                    for person in group:
                        players_eligible_to_group.remove(person)
                    print([person.name for person in group])
                    host_person_session_settings: PersonSessionSettings = session.exec(
                        select(PersonSessionSettings).filter(
                            (PersonSessionSettings.person_id == group[0].id)
                            & (PersonSessionSettings.time_slot_id == time_slot.id)
                        )
                    ).first()
                    host_person_session_settings.group_hosting_mode = GroupHostingMode.HOSTING
                    host_person_session_settings.group_members = group[1:]
                    session.add(host_person_session_settings)
                    for person in group[1:]:
                        person_session_settings: PersonSessionSettings = session.exec(
                            select(PersonSessionSettings).filter(
                                (PersonSessionSettings.person_id == person.id)
                                & (PersonSessionSettings.time_slot_id == time_slot.id)
                            )
                        ).first()
                        person_session_settings.group_hosting_mode = GroupHostingMode.JOINED
                        session.add(person_session_settings)

        session.commit()


def data_generation_main(args: argparse.Namespace) -> None:
    create_simulated_player_data(args)


# endregion


# region Game Allocator
person_id_t: TypeAlias = int
table_allocation_id_t: TypeAlias = int
time_slot_id_t: TypeAlias = int
game_id_t: TypeAlias = int
preference_score_t: TypeAlias = Literal[0, 1, 2, 3, 4, 5, 20] | float  # 0.5 = overflow


@total_ordering
@dataclass(eq=False)
class Tier:
    raw_preference: int | float  # 0.5 = overflow
    rank: int
    compensation: float = 0

    @property
    def is_golden_d20(self) -> bool:
        return self.rank == 20

    @property
    def is_zero(self) -> bool:
        return self.rank == 0 and self.raw_preference == 0

    # Sum of ranking (0, 1, 2, 3, 4, 5, 20 for d20) + compensation
    # Note that someone with only N different tiers, regardless of whether they're 1, 2, 4, etc will have N different ranks
    @property
    def value(self) -> float:
        if self.is_zero or self.raw_preference < 1:
            # Zero, or in the case of overflow - which is always 0.5, no value
            return 0
        # The fudge factor means that two 4s is better than a 5 and a 3, for example
        # TODO: This doesn't actually work if we don't have a swapping stage that considers new sums
        fudge = 0
        # fudge = {
        #     5: 0.07,
        #     4: 0.13,
        #     3: 0.18,
        #     2: 0.22,
        #     1: 0.25,
        # }.get(self.rank, 0)
        return self.rank + self.compensation + fudge

    def __eq__(self, other: Self) -> bool:
        if self.is_golden_d20 != other.is_golden_d20:
            return False
        return self.value == other.value

    def __lt__(self, other: Self) -> bool:
        if self.is_golden_d20 and not other.is_golden_d20:
            return False
        elif not self.is_golden_d20 and other.is_golden_d20:
            return True
        return self.value < other.value


class AllocationPriorityMode(enum.Enum):
    RANDOM = enum.auto()
    BY_PLAYERS_TO_OPTIMAL = enum.auto()


class TieredPreferences:
    def __init__(
        self,
        *,
        preferences: dict[table_allocation_id_t, preference_score_t],
        average_compensation: float,
        table_allocations: list[TableAllocationWithExtra],
    ) -> None:
        self.preferences = preferences
        self.average_compensation = average_compensation
        self.table_allocations = table_allocations
        print("Setting up tiered preferences")
        self.tier_list = self._init_tier_list()
        pprint(self.tier_list)
        self.tier_by_table_allocation_id = {
            table_allocation_id: tier
            for tier, table_allocation_ids in self.tier_list
            for table_allocation_id in table_allocation_ids
        }

    @property
    def has_d20(self) -> bool:
        return any(tier.is_golden_d20 for tier, _ in self.tier_list)

    def get_tier(self, table_allocation_id: table_allocation_id_t) -> Tier:
        return self.tier_by_table_allocation_id[table_allocation_id]

    def _init_tier_list(self) -> list[tuple[Tier, list[table_allocation_id_t]]]:
        preferences = self.preferences.copy()

        # Add missing preferences
        for table_allocation in self.table_allocations:
            if table_allocation.id not in preferences:
                preferences[table_allocation.id] = 3

        # Sort preferences by value
        ordered_preferences = sorted(
            preferences.items(),
            key=lambda x: x[1],
            reverse=True,  # Higher is first
        )
        grouped_preferences = [
            (g_key, [ta_id for ta_id, _ in g_items])
            for g_key, g_items in groupby(ordered_preferences, key=lambda x: x[1])
        ]
        number_of_tiers = len(grouped_preferences)
        starts_with_d20 = grouped_preferences[0][0] == 20
        ends_with_0 = grouped_preferences[-1][0] == 0
        rankings = (([20] if starts_with_d20 else []) + list(range(5, -2, -1)))[:number_of_tiers]
        if ends_with_0:
            rankings[-1] = 0
        assert len(rankings) == number_of_tiers

        # Assign tiers
        tier_list = []
        for ranking, (raw_score, table_allocation_ids) in zip(rankings, grouped_preferences):
            tier = Tier(
                raw_preference=raw_score,
                rank=ranking if raw_score >= 1 else 0,
                compensation=self.average_compensation,
            )
            tier_list.append((tier, table_allocation_ids))
        return tier_list

    def __repr__(self) -> str:
        return f"TieredPreferences({self.tier_list})"


@dataclass
class Group:
    person_ids: list[person_id_t]
    tiered_preferences: TieredPreferences = None

    @classmethod
    def from_person_and_session_settings(
        cls,
        person: PersonWithExtra,
        session_settings: PersonSessionSettingsWithExtra | time_slot_id_t,
        table_allocations: list[TableAllocationWithExtra],
        preference_overrides: dict[table_allocation_id_t, preference_score_t] = None,
    ) -> Self:
        if isinstance(session_settings, time_slot_id_t):
            persons = [person]
        else:
            persons = [person] + (
                list(session_settings.group_members)
                if session_settings.group_hosting_mode == GroupHostingMode.HOSTING
                else []
            )
        person_ids = {person.id for person in persons}
        # Just in case, to deduplicate
        persons = [[p for p in persons if p.id == person_id][0] for person_id in person_ids]
        preferences = {
            session_preference.table_allocation_id: session_preference.preference
            for session_preference in person.session_preferences
            if session_preference.table_allocation.time_slot_id
            == (session_settings if isinstance(session_settings, time_slot_id_t) else session_settings.time_slot_id)
        }
        if preference_overrides is not None:
            preferences.update(preference_overrides)
        average_compensation = sum([person.compensation for person in persons]) / len(persons)
        return cls(
            person_ids=person_ids,
            tiered_preferences=TieredPreferences(
                preferences=preferences,
                average_compensation=average_compensation,
                table_allocations=table_allocations,
            ),
        )

    def __len__(self) -> int:
        return len(self.person_ids)

    @property
    def size(self) -> int:
        return len(self.person_ids)


def sums_possible_with_numbers(numbers: list[int]) -> set[int]:
    result = {0}
    for combination_size in range(1, len(numbers) + 1):
        for combination in itertools.combinations(numbers, combination_size):
            result.add(sum(combination))
    return result


def sums_extractable(numbers: list[int], maximum: int) -> set[int]:
    return {s for s in sums_possible_with_numbers(numbers) if s <= maximum}


@dataclass
class CurrentGameAllocation:
    table_allocation: TableAllocationWithExtra
    groups: list[Group] = field(default_factory=list)

    def value_of_group(self, group: Group) -> Tier:
        return group.tiered_preferences.get_tier(self.table_allocation.id)

    def could_fit_group(self, group: Group) -> bool:
        return self.current_players + group.size <= self.table_allocation.game.maximum_players

    @property
    def value(self) -> float:
        return sum(self.value_of_group(group).value for group in self.groups)

    @property
    def current_players(self) -> int:
        return sum(group.size for group in self.groups)

    @property
    def maximum_players(self) -> int:
        return self.table_allocation.game.maximum_players

    @property
    def minimum_players(self) -> int:
        return self.table_allocation.game.minimum_players

    @property
    def optimal_players(self) -> int:
        return self.table_allocation.game.optimal_players

    def __repr__(self) -> str:
        return f"{self.table_allocation.game.title} [{self.table_allocation.id}] ({self.current_players}/{self.maximum_players})"

    def __str__(self) -> str:
        return f"{self.table_allocation.game.title} [{self.table_allocation.id}] ({self.current_players}/{self.maximum_players})"


@total_ordering
@dataclass(eq=False)
class TrialScore:
    score: float
    number_of_unfilled_tables: int

    def __lt__(self, other: Self) -> bool:
        if self.score == other.score:
            return self.number_of_unfilled_tables > other.number_of_unfilled_tables
        return self.score < other.score

    def __eq__(self, other: Self) -> bool:
        return self.score == other.score and self.number_of_unfilled_tables == other.number_of_unfilled_tables

    def __repr__(self) -> str:
        return f"{self.score}|{self.number_of_unfilled_tables}"


@dataclass
class GameAllocationResults:
    current_allocations: dict[table_allocation_id_t, CurrentGameAllocation]
    compensation_values: dict[person_id_t, int]
    d20s_spent: dict[person_id_t, int]


class GameAllocator:
    def __init__(self, engine: Engine, time_slot_id: time_slot_id_t) -> None:
        self.engine = engine
        self.time_slot_id = time_slot_id
        # Get all the data we need from the database to do the allocation
        self.table_allocations = self._init_table_allocations()
        self.table_allocations_map = {
            table_allocation.id: table_allocation for table_allocation in self.table_allocations
        }
        self.groups = self._init_groups()
        self.gamemasters_by_table_allocation_id = self._init_game_masters_by_table_allocation_id()
        self.current_allocations: dict[table_allocation_id_t, CurrentGameAllocation] = {}

        self.summary_dir = Path("summaries")
        if self.summary_dir.exists():
            shutil.rmtree(self.summary_dir)
        self.summary_dir.mkdir(parents=True)

    # INITIALIZATION
    def _init_table_allocations(self) -> list[TableAllocationWithExtra]:
        with Session(self.engine) as session:
            # All table allocations
            return [
                TableAllocationWithExtra.model_validate(table_allocation)
                for table_allocation in session.exec(
                    select(TableAllocation).filter(TableAllocation.time_slot_id == self.time_slot_id)
                ).all()
            ]

    def _init_groups(self) -> list[Group]:
        with Session(self.engine) as session:
            # People GMing this session
            gm_ids = [ta.game.gamemaster_id for ta in self.table_allocations]
            # All groups
            solo_or_hosts: list[tuple[Person, PersonSessionSettings]] = session.exec(
                select(Person, PersonSessionSettings)
                .join(Person, Person.id == PersonSessionSettings.person_id)
                .filter(
                    (PersonSessionSettings.time_slot_id == self.time_slot_id)
                    & (
                        (
                            # Solo players
                            (PersonSessionSettings.checked_in)
                            & (PersonSessionSettings.group_hosting_mode == GroupHostingMode.NOT_IN_GROUP)
                        )
                        # Hosts
                        | (PersonSessionSettings.group_hosting_mode == GroupHostingMode.HOSTING)
                    )
                    & col(Person.id).not_in(gm_ids)
                )
            ).all()
            overflow_table_allocation_id = session.exec(
                select(TableAllocation.id).filter(
                    (TableAllocation.game_id == 0) & (TableAllocation.time_slot_id == self.time_slot_id)
                )
            ).first()
            preference_overrides = {overflow_table_allocation_id: 0.5}
            return [
                Group.from_person_and_session_settings(
                    PersonWithExtra.model_validate(person),
                    PersonSessionSettingsWithExtra.model_validate(person_session_settings),
                    self.table_allocations,
                    preference_overrides=preference_overrides,
                )
                for person, person_session_settings in solo_or_hosts
            ]

    def _init_game_masters_by_table_allocation_id(self) -> dict[table_allocation_id_t, Group]:
        with Session(self.engine) as session:

            def session_settings_for_gm(gm: PersonWithExtra) -> PersonSessionSettingsWithExtra | time_slot_id_t:
                print("Checking session settings for", gm)
                possible_session_settings = [ss for ss in gm.session_settings if ss.time_slot_id == self.time_slot_id]
                if not possible_session_settings:
                    return self.time_slot_id
                assert len(possible_session_settings) == 1
                return PersonSessionSettingsWithExtra.model_validate(possible_session_settings[0])

            overflow_table_allocation_id = session.exec(
                select(TableAllocation.id).filter(TableAllocation.game_id == 0)
            ).first()
            preference_overrides = {overflow_table_allocation_id: 0.5}
            return {
                table_allocation.id: Group.from_person_and_session_settings(
                    gm := PersonWithExtra.model_validate(
                        session.get(Person, table_allocation.game.gamemaster.id)
                    ),  # Can't have stuff detached!
                    session_settings_for_gm(gm),
                    self.table_allocations,
                    preference_overrides=preference_overrides,
                )
                for table_allocation in self.table_allocations
            }

    def _init_current_allocations(self) -> dict[table_allocation_id_t, CurrentGameAllocation]:
        return {
            table_allocation.id: CurrentGameAllocation(table_allocation=table_allocation)
            for table_allocation in self.table_allocations
        }

    # ALLOCATION
    def allocate(self, *, n_trials: int = 1000) -> GameAllocationResults:
        best_result: dict[table_allocation_id_t, CurrentGameAllocation] | None = None
        best_score: TrialScore | None = None
        for trial_seed in range(100, 100 + n_trials):
            random.seed(trial_seed)
            trial_results = self._allocate_trial()
            trial_score = self._score_trial(trial_results)
            if best_score is None or trial_score > best_score:
                best_result = trial_results
                best_score = trial_score
                self._summary(best_result, label=f"trial_{trial_seed}.score_{trial_score}")
        compensation_values = self._get_compensation_values(best_result)
        d20s_spent = self._get_d20s_spent(best_result)
        pprint(compensation_values)
        return GameAllocationResults(best_result, compensation_values, d20s_spent)

    def _allocate_trial(self) -> dict[table_allocation_id_t, CurrentGameAllocation]:
        # Set up empty allocations
        self.current_allocations = self._init_current_allocations()

        # We want to allocate all the groups to tables
        # STAGE 1 - Allocate D20 holders
        d20_groups = [group for group in self.groups if group.tiered_preferences.has_d20]
        # print(len(d20_groups), "D20 groups")
        # print(len(self.groups), "Total groups")
        random.shuffle(d20_groups)
        for group in d20_groups:
            allocated_table_id = self._allocate_single_group(group)
            if allocated_table_id is None:
                # print("!R!@$!$!@$!@$!!", group)
                raise ValueError("D20 group could not be allocated")

        # print("D20 groups allocated")
        # pprint(self.current_allocations)

        # STAGE 2 - Allocate non-D20 holders
        non_d20_groups = [group for group in self.groups if not group.tiered_preferences.has_d20]
        random.shuffle(non_d20_groups)
        for group in non_d20_groups:
            allocated_table_id = self._allocate_single_group(group)
            if allocated_table_id is None:
                # print("!R!@$!$!@$!@$!!", group)
                raise ValueError("Non-D20 group could not be allocated")

        print("Pre-filled tables")
        pprint(self.current_allocations)

        # STAGE 3 - Try to move players to underfilled tables
        insufficiently_filled_tables = [
            current_allocation
            for current_allocation in self.current_allocations.values()
            if current_allocation.current_players < current_allocation.minimum_players
        ]
        # Sort by how close to minimum they are
        insufficiently_filled_tables = sorted(
            insufficiently_filled_tables,
            key=lambda ca: ca.minimum_players - ca.current_players,
        )
        unfillable_tables: list[CurrentGameAllocation] = []
        print("Insufficiently filled tables", insufficiently_filled_tables)
        print("----")
        for current_allocation in insufficiently_filled_tables:
            print("Trying to fill", current_allocation)
            allocated_table_id = self._try_to_fill_table(current_allocation)
            if not allocated_table_id:
                print("Couldn't fill", current_allocation)
                unfillable_tables.append(current_allocation)
            else:
                print("Filled", current_allocation)
            print("----")

        # STAGE 3.5? - Try to combine otherwise unfillable tables

        # STAGE 4 - Move players from unfillable tables to other tables
        unfillable_ids = {current_allocation.table_allocation.id for current_allocation in unfillable_tables}
        for current_allocation in unfillable_tables:
            print("Trying to move players from", current_allocation)
            # Allocate the GM
            allocated_table_id = self._allocate_single_group(
                self.gamemasters_by_table_allocation_id[current_allocation.table_allocation.id],
                allow_bumps=False,
                blocked_table_allocation_ids=unfillable_ids,
                priority_mode=AllocationPriorityMode.BY_PLAYERS_TO_OPTIMAL,
            )
            if allocated_table_id is None:
                raise ValueError("Unfillable GM could not be allocated")
            print("Moved GM", self.gamemasters_by_table_allocation_id[current_allocation.table_allocation.id])

            # And allocate all the remaining players
            for group in current_allocation.groups:
                allocated_table_id = self._allocate_single_group(
                    group,
                    allow_bumps=False,
                    blocked_table_allocation_ids=unfillable_ids,
                    priority_mode=AllocationPriorityMode.BY_PLAYERS_TO_OPTIMAL,
                )
                if allocated_table_id is None:
                    raise ValueError("Unfillable group could not be allocated")
            current_allocation.groups = []
            print("Moved players from", current_allocation)
            print("----")

        return self.current_allocations

    def _order_table_allocation_ids(
        self,
        table_allocation_ids: list[table_allocation_id_t],
        priority_mode: AllocationPriorityMode,
    ) -> list[table_allocation_id_t]:
        if priority_mode == AllocationPriorityMode.RANDOM:
            return random.sample(table_allocation_ids, len(table_allocation_ids))
        elif priority_mode == AllocationPriorityMode.BY_PLAYERS_TO_OPTIMAL:
            return sorted(
                table_allocation_ids,
                key=lambda ta_id: self.current_allocations[ta_id].current_players
                - self.current_allocations[ta_id].optimal_players,
            )
        else:
            raise ValueError(f"Unknown priority mode: {priority_mode}")

    def _allocate_single_group(
        self,
        group: Group,
        *,
        blocked_table_allocation_ids: set[table_allocation_id_t] | None = None,
        allow_bumps: bool = True,
        minimum_tier: Tier | None = None,
        priority_mode: AllocationPriorityMode = AllocationPriorityMode.RANDOM,
    ) -> table_allocation_id_t | None:
        if blocked_table_allocation_ids is None:
            blocked_table_allocation_ids = set()

        for tier, table_allocation_ids in group.tiered_preferences.tier_list:
            if tier.is_zero or (minimum_tier is not None and tier < minimum_tier):
                continue

            # STAGE 1 - FREE SPACE ALLOCATION
            # Greedily allocate to the first table that fits within this tier
            for table_allocation_id in self._order_table_allocation_ids(table_allocation_ids, priority_mode):
                if table_allocation_id in blocked_table_allocation_ids:
                    continue

                current_allocation = self.current_allocations[table_allocation_id]
                if current_allocation.could_fit_group(group):
                    current_allocation.groups.append(group)
                    return table_allocation_id

            if not allow_bumps:
                continue

            # STAGE 2 - BUMPING ALLOCATION
            # If we couldn't allocate to a table without removing someone
            # we get less polite - try to push groups out without reducing the tier value
            for table_allocation_id in self._order_table_allocation_ids(table_allocation_ids, priority_mode):
                if table_allocation_id in blocked_table_allocation_ids:
                    continue

                current_allocation = self.current_allocations[table_allocation_id]
                other_groups_at_table = current_allocation.groups
                for other_group in other_groups_at_table:
                    # In order for the other group to be a possible candidate to move, it must be of an equal or lower tier
                    other_group_tier_lower = current_allocation.value_of_group(
                        other_group
                    ) <= current_allocation.value_of_group(group)
                    if not other_group_tier_lower:
                        continue
                    # And us joining the table must not put too many people at the table
                    could_fit_if_swapped = (
                        current_allocation.current_players - other_group.size + group.size
                    ) <= current_allocation.maximum_players
                    if not could_fit_if_swapped:
                        continue
                    # If they're a possible candidate, see if they can be moved without reducing their tier or bumping someone else
                    if (
                        self._allocate_single_group(
                            other_group,
                            blocked_table_allocation_ids={table_allocation_id},
                            allow_bumps=False,
                            minimum_tier=current_allocation.value_of_group(other_group),
                        )
                        is not None
                    ):
                        current_allocation.groups.remove(other_group)
                        current_allocation.groups.append(group)
                        return table_allocation_id

        # We couldn't allocate the group - there is no space or no game above zero preference
        return None

    def _try_to_fill_table(self, underfilled: CurrentGameAllocation) -> bool:
        number_of_players_required = underfilled.minimum_players - underfilled.current_players
        number_of_players_maximum = underfilled.maximum_players - underfilled.current_players
        required_player_numbers_to_take = set(range(number_of_players_required, number_of_players_maximum + 1))
        candidate_groups: dict[table_allocation_id_t, tuple[int, list[Group]]] = {}

        # Find tables that are over the sweet spot as possible sources of players
        tables_over_sweet_spot = [
            current_allocation
            for current_allocation in self.current_allocations.values()
            if current_allocation.current_players > current_allocation.optimal_players
        ]
        print("Tables over sweet spot", tables_over_sweet_spot)

        # Get groups that could be moved to the underfilled table
        for table_allocation_id in random.sample(
            [ca.table_allocation.id for ca in tables_over_sweet_spot], len(tables_over_sweet_spot)
        ):
            candidate_table = self.current_allocations[table_allocation_id]
            groups_at_table = candidate_table.groups
            for group in groups_at_table:
                # Check if removing the group wouldn't make the table underfilled
                if candidate_table.current_players - group.size < candidate_table.minimum_players:
                    continue
                # Check if the group's preference for the underfilled table is at least as high as the current table
                if group.tiered_preferences.get_tier(underfilled.table_allocation.id) < candidate_table.value_of_group(
                    group
                ):
                    continue
                if table_allocation_id not in candidate_groups:
                    allowable_players_to_take = candidate_table.current_players - candidate_table.minimum_players
                    candidate_groups[table_allocation_id] = (allowable_players_to_take, [])
                candidate_groups[table_allocation_id][1].append(group)

        def all_table_subset_combinations(groups: list[Group], max_player_count: int) -> list[tuple[Group, ...]]:
            result = [()]  # Empty list - i.e. no groups
            for i in range(1, len(groups) + 1):
                subsets = itertools.combinations(groups, i)
                for subset in subsets:
                    if sum([group.size for group in subset]) <= max_player_count:
                        result.append(subset)
            return result

        print("Candidate groups")
        pprint(candidate_groups)
        candidate_subsets_by_table: dict[table_allocation_id_t, list[tuple[Group, ...]]] = {
            table_allocation_id: all_table_subset_combinations(groups, allowable_players_to_take)
            for table_allocation_id, (allowable_players_to_take, groups) in candidate_groups.items()
        }
        # print("Candidate subsets by table")
        # pprint(candidate_subsets_by_table)
        candidate_subsets_across_all = [
            list(zip(candidate_subsets_by_table.keys(), prod))
            for prod in itertools.product(*candidate_subsets_by_table.values())
        ]
        # print("Candidate subsets across all")
        # pprint(candidate_subsets_across_all)
        candidate_subsets_with_sufficient_players = [
            candidate_subset
            for candidate_subset in candidate_subsets_across_all
            if sum(  # Sum of all group sizes from all tables
                [
                    sum([group.size for group in groups])  # Sum of all group sizes from this table
                    for ta_id, groups in candidate_subset
                ]
            )
            in required_player_numbers_to_take
        ]
        # print("Candidate subsets with sufficient players")
        # pprint(candidate_subsets_with_sufficient_players)

        if not candidate_subsets_with_sufficient_players:
            return False

        # Now we have all the possible combinations of groups that could be moved to the underfilled table
        # Pick one at random
        chosen_subset = random.choice(candidate_subsets_with_sufficient_players)
        print("Chosen subset")
        pprint(chosen_subset)
        # And actually move the players
        for table_allocation_id, groups in chosen_subset:
            candidate_table = self.current_allocations[table_allocation_id]
            for group in groups:
                candidate_table.groups.remove(group)
                underfilled.groups.append(group)
                print("Moved", group, "to", underfilled)
        return True

    # SCORING
    def _score_trial(self, trial_results: dict[table_allocation_id_t, CurrentGameAllocation]) -> TrialScore:
        # TODO: Maybe just count the required compensation? Where we want to minimize the compensation
        score_value = sum(current_allocation.value for current_allocation in trial_results.values())
        return TrialScore(
            score=score_value,
            number_of_unfilled_tables=sum(
                current_allocation.current_players < current_allocation.minimum_players
                for current_allocation in trial_results.values()
            ),
        )

    def _get_compensation_values(
        self, trial_results: dict[table_allocation_id_t, CurrentGameAllocation]
    ) -> dict[person_id_t, int]:
        # Players get 1, 2, 3, ... points of compensation for each tier down from their highest from the game they've been allocated in
        # D20s get their D20 refunded and 6 points of compensation
        # GMs that didn't run get an extra point of compensation too
        result: dict = {}
        for current_allocation in trial_results.values():
            for group in current_allocation.groups:
                for person_id in group.person_ids:
                    allocated_tier_rank = group.tiered_preferences.get_tier(current_allocation.table_allocation.id).rank
                    highest_tier_rank = group.tiered_preferences.tier_list[0][0].rank
                    if allocated_tier_rank == 20:
                        allocated_tier_rank = 6
                    if highest_tier_rank == 20:
                        highest_tier_rank = 6
                    result[person_id] = highest_tier_rank - allocated_tier_rank
                    print(
                        "Compensation for",
                        person_id,
                        "is",
                        result[person_id],
                        "for",
                        current_allocation,
                        "which had",
                        group.tiered_preferences.get_tier(current_allocation.table_allocation.id),
                    )
        return result

    def _get_d20s_spent(
        self, trial_results: dict[table_allocation_id_t, CurrentGameAllocation]
    ) -> dict[person_id_t, int]:
        result: dict = {}
        for current_allocation in trial_results.values():
            for group in current_allocation.groups:
                if (
                    group.tiered_preferences.has_d20
                    and group.tiered_preferences.get_tier(current_allocation.table_allocation.id).is_golden_d20
                ):
                    for person_id in group.person_ids:
                        result[person_id] = 1
                        print(
                            "D20 spent by",
                            person_id,
                            "for",
                            current_allocation,
                            "which had",
                            group.tiered_preferences.get_tier(current_allocation.table_allocation.id),
                        )
        return result

    def _summary(
        self, trial_results: dict[table_allocation_id_t, CurrentGameAllocation], label: str = "latest"
    ) -> None:
        current_allocations = list(trial_results.values())

        game_centric_rows: list[dict[str, Any]] = []
        for current_allocation in current_allocations:
            game_centric_rows.append(
                {
                    "game": current_allocation.table_allocation.game.title,
                    "current_players": current_allocation.current_players,
                    "minimum_players": current_allocation.minimum_players,
                    "optimal_players": current_allocation.optimal_players,
                    "maximum_players": current_allocation.maximum_players,
                    "value": current_allocation.value,
                }
            )

        game_centric_df = pl.DataFrame(game_centric_rows)
        game_centric_df.write_csv(self.summary_dir / f"games.{label}.csv")

        group_centric_rows: list[dict[str, Any]] = []
        for current_allocation in current_allocations:
            for group in current_allocation.groups:
                group_centric_rows.append(
                    {
                        "number_of_players": group.size,
                        "tier_rank": current_allocation.value_of_group(group).rank,
                    }
                )
        group_centric_df = pl.DataFrame(group_centric_rows)
        group_centric_df.write_csv(self.summary_dir / f"groups.{label}.csv")
        group_centric_df.group_by("tier_rank").agg(pl.len()).sort(pl.col("tier_rank")).write_csv(
            self.summary_dir / f"groups_tier_counts.{label}.csv"
        )

        player_centric_df = group_centric_df.select(
            pl.exclude("number_of_players").repeat_by("number_of_players").explode()
        )
        player_centric_df.write_csv(self.summary_dir / f"players.{label}.csv")
        # Bar chart of number of players per tier
        player_centric_df.group_by("tier_rank").agg(pl.len()).sort(pl.col("tier_rank")).write_csv(
            self.summary_dir / f"players_tier_counts.{label}.csv"
        )


def end_to_end_main(args: argparse.Namespace) -> None:
    # Setup
    mock_runtime_engine = create_engine("sqlite:///mock_runtime.db")
    SQLModel.metadata.create_all(mock_runtime_engine)

    all_time_slot_ids = range(1, 5 + 1)
    first_time_slot_ids = [1]

    # Doing each round of allocations
    for time_slot_id in first_time_slot_ids:
        # allocation_results = allocate(mock_runtime_engine, time_slot_id)
        game_allocator = GameAllocator(mock_runtime_engine, time_slot_id)
        allocation_results = game_allocator.allocate(n_trials=args.n_trials)
        pprint(allocation_results.current_allocations)
        pprint(allocation_results.compensation_values)
        pprint(allocation_results.d20s_spent)


# endregion

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    # data_generation
    data_generation_parser = subparsers.add_parser("data_generation")
    data_generation_parser.set_defaults(func=data_generation_main)
    data_generation_parser.add_argument("--force-recreate", action="store_true")
    data_generation_parser.add_argument("--n-players", type=int, default=160)  # Inclusive of existing GMs
    data_generation_parser.add_argument("--n-with-golden-d20", type=int, default=30)
    data_generation_parser.add_argument("--n-groups-of-2", type=int, default=10)  # 2 * 10 = 20
    data_generation_parser.add_argument("--n-groups-of-3", type=int, default=10)  # 3 * 10 = 30
    # end_to_end
    end_to_end_parser = subparsers.add_parser("end_to_end")
    end_to_end_parser.add_argument("--n-trials", type=int, default=1)
    end_to_end_parser.set_defaults(func=end_to_end_main)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()
