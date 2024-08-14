import tempfile
from pathlib import Path
from typing import Self, TypedDict

import polars as pl
import requests
from sqlmodel import SQLModel

from convergence_games.db.extra_types import GameCrunch, GameNarrativism, GameTone
from convergence_games.db.models import ContentWarning, Game, Genre, Person, System, TableAllocation

# TODO: Decide consistent edition names
SYSTEM_NAME_MAP = {
    "Call of Cthulhu": "Call of Cthulhu 7e",
    "Call of Cthulhu 7th Edition": "Call of Cthulhu 7e",
    "Call of Cthulhu 7th ed": "Call of Cthulhu 7e",
    "5e": "D&D 5e",
    "DND 5e": "D&D 5e",
    "DnD 5e": "D&D 5e",
    "5th Edition Dungeons and Dragons": "D&D 5e",
    "5th Edition Dungeons & Dragons": "D&D 5e",
    "D&D5e": "D&D 5e",
    "Dungeons and Dragons 5e": "D&D 5e",
    "Dungeons and Dragons 5e (One D&D)": "D&D 5e",
    "Dnd 5e adjacent": "D&D 5e",
    "Dnd 5e (pregens provided)": "D&D 5e",
    "D&D (5e)": "D&D 5e",
    "Monsterhearts 2nd edition": "Monsterhearts 2",
    "Motherhship 1E": "Mothership 1E",
    "overkill 2nd Edition": "Overkill 2nd Edition",
    "Pathfinder 2nd Edition": "Pathfinder 2e",
    "Paranoia 2ed": "Paranoia 2nd Edition",
    "Homebrew system": "Sulphur",
    "Starfinder 2e Playtest": "Starfinder 2e",
    "Starfinder Second Edition Playtest": "Starfinder 2e",
    "Prismatic (Formerly known as Memories of Stone)": "Prismatic (Formerly Memories of Stone)",
    "Daggerheart Open Beta 1.4.2": "Daggerheart",
    "Tales System (RSS)": "Tales System",
}


DEFAULT_GAME_SHEET_URL = "https://docs.google.com/spreadsheets/d/1jQCA-ZqUjw6C5D8koAS6RiiZUvu5m7L0xqqjL06DvFA/export?gid=1424049540&format=csv"
DEFAULT_SCHEDULE_SHEET_URL = (
    "https://docs.google.com/spreadsheets/d/1_AZHowZkvRU_wBGnoaqV-uQFpXvTFXlr8zZBcAsS6Tc/export?gid=0&format=csv"
)


class GameResponse(TypedDict):
    running: bool
    id: int
    gamemaster_email: str
    gamemaster_name: str
    title: str
    system_name: str
    genre_names: list[str]
    description: str
    crunch: GameCrunch
    narrativism: GameNarrativism
    tone: GameTone
    age_suitability: str
    content_warnings: list[str]
    minimum_players: int
    optimal_players: int
    maximum_players: int
    nz_made: bool
    designer_run: bool


class ScheduleResponse(TypedDict):
    table_number: int
    session_id: int
    game_id: int


class GoogleSheetsImporter:
    def __init__(self, *, game_csv_path: Path, schedule_csv_path: Path):
        self.game_df = pl.read_csv(game_csv_path)
        self.schedule_df = pl.read_csv(schedule_csv_path)

    @classmethod
    def from_urls(cls, *, game_sheet_url: str | None = None, schedule_sheet_url: str | None = None) -> Self:
        if game_sheet_url is None:
            game_sheet_url = DEFAULT_GAME_SHEET_URL
        if schedule_sheet_url is None:
            schedule_sheet_url = DEFAULT_SCHEDULE_SHEET_URL

        with tempfile.NamedTemporaryFile() as game_csv_file, tempfile.NamedTemporaryFile() as schedule_csv_file:
            game_csv_file.write(requests.get(game_sheet_url).content)
            game_csv_path = Path(game_csv_file.name)
            schedule_csv_file.write(requests.get(schedule_sheet_url).content)
            schedule_csv_path = Path(schedule_csv_file.name)

            return cls(
                game_csv_path=game_csv_path,
                schedule_csv_path=schedule_csv_path,
            )

    def _transform_game_sheet(self, df: pl.DataFrame) -> pl.DataFrame:
        def replace_seven_plus(col_name: str) -> pl.Expr:
            return pl.col(col_name).cast(str).replace({"7+": 7}).cast(pl.Int8)

        result = df.select(
            pl.col("Running").cast(bool).alias("running"),
            pl.col("ID").cast(pl.Int32).alias("id"),
            pl.col("Email address").alias("gamemaster_email"),
            pl.col("Full Name").alias("gamemaster_name"),
            pl.col("Game Title").str.strip_chars().alias("title"),
            pl.col("System").str.strip_chars().replace(SYSTEM_NAME_MAP).alias("system_name"),
            pl.col("Genre(s)").str.split(", ").alias("genre_names"),
            pl.col("Description").alias("description"),
            pl.col("Crunch/Weight")
            .cast(str)
            .replace({"1": GameCrunch.LIGHT.value, "2": GameCrunch.MEDIUM.value, "3": GameCrunch.HEAVY.value})
            .alias("crunch"),
            pl.col("Narrativist vs Gameist Spectrum")
            .cast(str)
            .replace(
                {
                    "1": GameNarrativism.NARRATIVIST.value,
                    "2": GameNarrativism.BALANCED.value,
                    "3": GameNarrativism.GAMEIST.value,
                }
            )
            .alias("narrativism"),
            pl.col("Tone").alias("tone"),
            pl.col("Age Suitability").alias("age_suitability"),
            pl.col("Content Warnings").str.split(", ").alias("content_warnings"),
            replace_seven_plus("Player Count Ranges [Minimum]").alias("minimum_players"),
            replace_seven_plus("Player Count Ranges [Sweet Spot]").alias("optimal_players"),
            replace_seven_plus("Player Count Ranges [Maximum]").alias("maximum_players"),
            pl.col("Is this system NZ made, or your own creation? (We'd love to give it a special shout out if so!)")
            .str.contains("My own system that I am running|Kiwi made")
            .alias("nz_made"),
            pl.col("Is this system NZ made, or your own creation? (We'd love to give it a special shout out if so!)")
            .str.contains("My own system that I am running")
            .alias("designer_run"),
        ).filter(pl.col("running"))
        print(len(result), "games imported")

        return result

    def _import_game_sheet(self) -> list[SQLModel]:
        df = self._transform_game_sheet(self.game_df)
        all_rows: list[GameResponse] = list(df.iter_rows(named=True))

        genre_names = df["genre_names"].explode().unique().to_list()
        genre_dbos = [Genre(name=name) for name in genre_names if name is not None]
        system_names = df["system_name"].unique().to_list()
        system_dbos = [System(name=name) for name in system_names if name is not None]
        content_warnings = df["content_warnings"].explode().unique().to_list()
        content_warning_dbos = [ContentWarning(name=name) for name in content_warnings if name is not None]
        gamemaster_dbos = list(
            {
                row["gamemaster_email"]: Person(name=row["gamemaster_name"], email=row["gamemaster_email"])
                for row in all_rows
            }.values()
        )
        game_dbos = [
            Game(
                id=row["id"],
                title=row["title"],
                description=row["description"],
                crunch=row["crunch"],
                narrativism=row["narrativism"],
                tone=row["tone"],
                age_suitability=row["age_suitability"],
                minimum_players=row["minimum_players"],
                optimal_players=row["optimal_players"],
                maximum_players=row["maximum_players"],
                nz_made=row["nz_made"],
                designer_run=row["nz_made"],
                genres=[genre for genre in genre_dbos if genre.name in row["genre_names"]]
                if row["genre_names"]
                else [],
                content_warnings=[cw for cw in content_warning_dbos if cw.name in row["content_warnings"]]
                if row["content_warnings"]
                else [],
                gamemaster=next(gm for gm in gamemaster_dbos if gm.email == row["gamemaster_email"]),
                system=next(sys for sys in system_dbos if sys.name == row["system_name"]),
            )
            for row in all_rows
        ]

        return [
            *genre_dbos,
            *system_dbos,
            *content_warning_dbos,
            *gamemaster_dbos,
            *game_dbos,
        ]

    def _transform_schedule_sheet(self, df: pl.DataFrame) -> pl.DataFrame:
        def get_table_number(row_name: str) -> pl.Expr:
            # Table numbers are in the format: "123" or "Note - 123"
            return pl.col(row_name).str.extract(r"(\d+)$").cast(pl.Int8)

        def get_game_id(row_name: str) -> pl.Expr:
            # Game IDs are in the format: "123 - Game Title"
            return pl.col(row_name).str.extract(r"^(\d+)").cast(pl.Int32)

        per_table = df.select(
            pl.col("Tables").alias("table_number"),
            pl.col("Session 1 (3 hours)").alias("1"),
            pl.col("Session 2 (3 hours)").alias("2"),
            pl.col("Session 3 (4 hours)").alias("3"),
            pl.col("Session 4 (3 hours)").alias("4"),
            pl.col("Session 5 (4 hours)").alias("5"),
        )
        refined = per_table.select(
            get_table_number("table_number"),
            get_game_id("1"),
            get_game_id("2"),
            get_game_id("3"),
            get_game_id("4"),
            get_game_id("5"),
        )
        # Now we want to pivot the table so that we have a row for each game in each session
        # We can then filter out the rows where the game ID is null
        # Or duplicate games in the same session, keeping the first one
        result = (
            refined.melt(id_vars=["table_number"], variable_name="session_id", value_name="game_id")
            .filter(pl.col("game_id").is_not_null())
            .with_columns(pl.col("session_id").cast(pl.Int8))
            .unique(("session_id", "game_id"), keep="first", maintain_order=True)
        )
        return result

    def _import_schedule_sheet(self) -> list[SQLModel]:
        df = self._transform_schedule_sheet(self.schedule_df)
        all_rows: list[ScheduleResponse] = list(df.iter_rows(named=True))
        table_allocation_dbos = [
            TableAllocation(
                table_number=row["table_number"],
                time_slot_id=row["session_id"],
                game_id=row["game_id"],
                id=row["session_id"] * 10000 + row["game_id"],
            )
            for row in all_rows
        ]
        return table_allocation_dbos

    def import_all(self) -> list[SQLModel]:
        return [
            *self._import_game_sheet(),
            *self._import_schedule_sheet(),
        ]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--game-sheet-url",
        type=str,
        help="URL of the Google Sheet to import",
        default=DEFAULT_GAME_SHEET_URL,
    )
    parser.add_argument(
        "--schedule-sheet-url",
        type=str,
        help="URL of the Google Sheet to import",
        default=DEFAULT_SCHEDULE_SHEET_URL,
    )
    args = parser.parse_args()

    importer = GoogleSheetsImporter.from_urls(
        game_sheet_url=args.game_sheet_url,
        schedule_sheet_url=args.schedule_sheet_url,
    )
    for model in importer.import_all():
        print(model)
