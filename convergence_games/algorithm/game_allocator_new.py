import argparse
import random
import shutil
from dataclasses import dataclass, field
from functools import total_ordering
from itertools import groupby
from pathlib import Path
from pprint import pprint
from typing import Any, Literal, Self, TypeAlias

import polars as pl
from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine, func, select

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

        with Session(mock_base_engine) as session:
            session.add_all(ALL_BASE_DATA)
            dbos = GoogleSheetsImporter.from_urls().import_all()
            session.add_all(dbos)
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
        print("Rankings", rankings)
        print(grouped_preferences)

        # Assign tiers
        tier_list = []
        for ranking, (raw_score, table_allocation_ids) in zip(rankings, grouped_preferences):
            tier = Tier(
                raw_preference=raw_score,
                rank=ranking,
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
        session_settings: PersonSessionSettingsWithExtra,
        table_allocations: list[TableAllocationWithExtra],
        preference_overrides: dict[table_allocation_id_t, preference_score_t] = None,
    ) -> Self:
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
            if session_preference.table_allocation.time_slot_id == session_settings.time_slot_id
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
        return f"{self.table_allocation.game.title} ({self.current_players}/{self.maximum_players})"

    def __str__(self) -> str:
        return f"{self.table_allocation.game.title} ({self.current_players}/{self.maximum_players})"


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
                )
            ).all()
            overflow_table_allocation_id = session.exec(
                select(TableAllocation.id).filter(TableAllocation.game_id == 0)
            ).first()
            preference_overrides = {overflow_table_allocation_id: 0.5}
            return [
                Group.from_person_and_session_settings(
                    PersonWithExtra.model_validate(person),
                    PersonSessionSettingsWithExtra.model_validate(person_session_settings),
                    self.table_allocations,
                    preference_overrides=preference_overrides,
                )
                for person, person_session_settings in solo_or_hosts  # TODO: More than 1
            ]

    def _init_current_allocations(self) -> dict[table_allocation_id_t, CurrentGameAllocation]:
        return {
            table_allocation.id: CurrentGameAllocation(table_allocation=table_allocation)
            for table_allocation in self.table_allocations
        }

    # ALLOCATION
    def allocate(self, *, n_trials: int = 1000) -> dict[table_allocation_id_t, CurrentGameAllocation]:
        best_result: dict[table_allocation_id_t, CurrentGameAllocation] | None = None
        best_score: float | None = None
        for trial_seed in range(100, 100 + n_trials):
            random.seed(trial_seed)
            trial_results = self._allocate_trial()
            trial_score = self._score_trial(trial_results)
            if best_result is None or trial_score > best_score:
                best_result = trial_results
                best_score = trial_score
                self._summary(best_result, label=f"trial_{trial_seed}.score_{trial_score}")
        return best_result

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
            success = self._allocate_single_group(group)
            if not success:
                # print("!R!@$!$!@$!@$!!", group)
                raise ValueError("D20 group could not be allocated")

        # print("D20 groups allocated")
        # pprint(self.current_allocations)

        # STAGE 2 - Allocate non-D20 holders
        non_d20_groups = [group for group in self.groups if not group.tiered_preferences.has_d20]
        random.shuffle(non_d20_groups)
        for group in non_d20_groups:
            success = self._allocate_single_group(group)
            if not success:
                # print("!R!@$!$!@$!@$!!", group)
                raise ValueError("Non-D20 group could not be allocated")

        return self.current_allocations

    def _allocate_single_group(
        self,
        group: Group,
        *,
        blocked_table_allocation_ids: set[table_allocation_id_t] | None = None,
        allow_bumps: bool = True,
        minimum_tier: Tier | None = None,
    ) -> bool:
        if blocked_table_allocation_ids is None:
            blocked_table_allocation_ids = set()

        for tier, table_allocation_ids in group.tiered_preferences.tier_list:
            if tier.is_zero or (minimum_tier is not None and tier < minimum_tier):
                continue

            # STAGE 1 - FREE SPACE ALLOCATION
            # Greedily allocate to the first table that fits within this tier
            for table_allocation_id in random.sample(table_allocation_ids, len(table_allocation_ids)):
                if table_allocation_id in blocked_table_allocation_ids:
                    continue

                current_allocation = self.current_allocations[table_allocation_id]
                if current_allocation.could_fit_group(group):
                    current_allocation.groups.append(group)
                    return True

            if not allow_bumps:
                continue

            # STAGE 2 - BUMPING ALLOCATION
            # If we couldn't allocate to a table without removing someone
            # we get less polite - try to push groups out without reducing the tier value
            for table_allocation_id in random.sample(table_allocation_ids, len(table_allocation_ids)):
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
                    if self._allocate_single_group(
                        other_group,
                        blocked_table_allocation_ids={table_allocation_id},
                        allow_bumps=False,
                        minimum_tier=current_allocation.value_of_group(other_group),
                    ):
                        current_allocation.groups.remove(other_group)
                        current_allocation.groups.append(group)
                        return True

        # We couldn't allocate the group - there is no space or no game above zero preference
        return False

    # SCORING
    def _score_trial(self, trial_results: dict[table_allocation_id_t, CurrentGameAllocation]) -> float:
        # TODO: Maybe just count the required compensation? Where we want to minimize the compensation
        return sum(current_allocation.value for current_allocation in trial_results.values())

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
        pprint(allocation_results)


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
