from io import StringIO
from pathlib import Path
from typing import Iterator, TypedDict

import polars as pl
import requests
from sqlmodel import SQLModel

from convergence_games.db.extra_types import GameCrunch, GameNarrativism, GameTone
from convergence_games.db.models import ContentWarning, Game, Genre, Person, System

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


class GameResponse(TypedDict):
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


class GoogleSheetsImporter:
    def __init__(self, *, csv_path: Path | None = None, sheet_url: str | None = None):
        if not (csv_path or sheet_url):
            raise ValueError("Either csv_file or sheet_url must be provided")
        self.csv_path = csv_path
        self.sheet_url = sheet_url

    def _load_sheet(self) -> pl.DataFrame | None:
        if self.csv_path:
            return pl.read_csv(self.csv_path)

        r = requests.get(self.sheet_url)
        if r.status_code == 200:
            data = StringIO(r.content.decode("utf-8"))
            df = pl.read_csv(data)
            return df
        else:
            return None

    def _transform_sheet(self, df: pl.DataFrame) -> pl.DataFrame:
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

    def _rows_to_game_responses(self, df: pl.DataFrame) -> Iterator[GameResponse]:
        return df.iter_rows(named=True)

    def import_sheet(self) -> list[SQLModel]:
        df = self._transform_sheet(self._load_sheet())
        all_rows = list(self._rows_to_game_responses(df))

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


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sheet-url",
        type=str,
        help="URL of the Google Sheet to import",
        default="https://docs.google.com/spreadsheets/d/1jQCA-ZqUjw6C5D8koAS6RiiZUvu5m7L0xqqjL06DvFA/export?gid=1424049540&format=csv",
    )
    parser.add_argument(
        "--timetable-sheet-url",
        type=str,
        help="URL of the Google Sheet to import",
        default="https://docs.google.com/spreadsheets/d/1_AZHowZkvRU_wBGnoaqV-uQFpXvTFXlr8zZBcAsS6Tc/edit?gid=0#gid=0",
    )
    parser.add_argument("--csv_path", type=Path, help="Path to the CSV file to import", default=Path("games.csv"))
    args = parser.parse_args()

    csv_path: Path = args.csv_path

    # if not csv_path.exists():
    with open(csv_path, "wb") as f:
        sheet_contents = requests.get(args.sheet_url).content
        f.write(sheet_contents)

    importer = GoogleSheetsImporter(csv_path=csv_path)
    for model in importer.import_sheet():
        print(model)
