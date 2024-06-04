from pydantic import computed_field

from convergence_games.db.models import GameRead, Genre, Person, PersonRead, System, TableAllocationRead, TimeSlot


class PersonWithExtra(PersonRead):
    gmd_games: list["GameWithExtra"] = []


class TableAllocationWithSlot(TableAllocationRead):
    time_slot: TimeSlot

    @computed_field
    @property
    def slot_name(self) -> str:
        return self.time_slot.name

    @computed_field
    @property
    def time_range(self) -> str:
        return f"{self.time_slot.start_time.strftime("%A %H:%M")} - {self.time_slot.end_time.strftime("%H:%M")}"


class GameWithExtra(GameRead):
    genres: list[Genre] = []
    system: System
    gamemaster: Person
    table_allocations: list[TableAllocationWithSlot] = []

    @computed_field
    @property
    def times_available(self) -> list[str]:
        return [table_allocation.time_range for table_allocation in self.table_allocations]

    @computed_field
    @property
    def times_available_string(self) -> str:
        return ", ".join(self.times_available)

    @computed_field
    @property
    def genre_names(self) -> list[str]:
        return [genre.name for genre in self.genres]

    @computed_field
    @property
    def genre_names_string(self) -> str:
        return ", ".join(self.genre_names)

    @computed_field
    @property
    def system_name(self) -> str:
        return self.system.name

    @computed_field
    @property
    def game_master_name(self) -> str:
        return self.gamemaster.name

    @computed_field
    @property
    def game_master_id(self) -> int:
        return self.gamemaster.id
