import datetime as dt
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from convergence_games.db.enums import (
    SubmissionStatus,
)
from convergence_games.db.models import (
    ContentWarning,
    Event,
    Genre,
    System,
    SystemAlias,
    TimeSlot,
)


async def create_mock_data(transaction: AsyncSession) -> None:
    NZT = ZoneInfo("Pacific/Auckland")  # noqa: N806

    event = Event(
        name="Convergence 2025",
        description="",
        start_date=dt.datetime(2025, 9, 13, tzinfo=NZT),
        end_date=dt.datetime(2025, 9, 14, tzinfo=NZT),
        rooms=[],
        time_slots=[
            TimeSlot(
                name="Saturday Morning",
                start_time=dt.datetime(2025, 9, 13, 9, 0, tzinfo=NZT),
                end_time=dt.datetime(2025, 9, 13, 12, 0, tzinfo=NZT),
            ),
            TimeSlot(
                name="Saturday Afternoon",
                start_time=dt.datetime(2025, 9, 13, 13, 30, tzinfo=NZT),
                end_time=dt.datetime(2025, 9, 13, 16, 30, tzinfo=NZT),
            ),
            TimeSlot(
                name="Saturday Evening",
                start_time=dt.datetime(2025, 9, 13, 18, 0, tzinfo=NZT),
                end_time=dt.datetime(2025, 9, 13, 22, 0, tzinfo=NZT),
            ),
            TimeSlot(
                name="Sunday Morning",
                start_time=dt.datetime(2025, 9, 14, 9, 0, tzinfo=NZT),
                end_time=dt.datetime(2025, 9, 14, 12, 0, tzinfo=NZT),
            ),
            TimeSlot(
                name="Sunday Afternoon",
                start_time=dt.datetime(2025, 9, 14, 14, 30, tzinfo=NZT),
                end_time=dt.datetime(2025, 9, 14, 18, 30, tzinfo=NZT),
            ),
        ],
    )

    genres = [
        # Suggested genres
        Genre(name="Comedy", suggested=True),
        Genre(name="Cyberpunk", suggested=True),
        Genre(name="Dungeon Crawl", suggested=True),
        Genre(name="Fantasy", suggested=True),
        Genre(name="Grimdark", suggested=True),
        Genre(name="Historical", suggested=True),
        Genre(name="Horror", suggested=True),
        Genre(name="Mystery", suggested=True),
        Genre(name="Sci-Fi", suggested=True),
        Genre(name="Space Opera", suggested=True),
        Genre(name="Steampunk", suggested=True),
        Genre(name="Superhero", suggested=True),
        Genre(name="Western", suggested=True),
        # Other genres
        Genre(name="Action"),
        Genre(name="Cosmic Horror"),
        Genre(name="Dark"),
        Genre(name="Drama"),
        Genre(name="Heist"),
        Genre(name="Modern"),
        Genre(name="Post-Apocalyptic"),
        Genre(name="Pulp"),
        Genre(name="Romance"),
        Genre(name="Slasher"),
        Genre(name="Slice of Life"),
        Genre(name="Survival"),
        Genre(name="Sword & Sorcery"),
        Genre(name="Urban Fantasy"),
        Genre(name="Worldbuilding"),
    ]

    for genre in genres:
        genre.submission_status = SubmissionStatus.APPROVED

    systems = [
        System(
            name="Dungeons & Dragons 3.5e",
            aliases=[
                SystemAlias(name="D&D 3.5e"),
                SystemAlias(name="3.5e"),
                SystemAlias(name="DND 3.5e"),
                SystemAlias(name="DND 3.5"),
                SystemAlias(name="D&D 3.5"),
            ],
        ),
        System(
            name="Dungeons & Dragons 4e",
            aliases=[
                SystemAlias(name="D&D 4e"),
                SystemAlias(name="4e"),
                SystemAlias(name="DND 4e"),
                SystemAlias(name="DND 4"),
                SystemAlias(name="D&D 4th Edition"),
            ],
        ),
        System(
            name="Dungeons & Dragons 5e",
            aliases=[
                SystemAlias(name="D&D 5e"),
                SystemAlias(name="5e"),
                SystemAlias(name="DND 5e"),
                SystemAlias(name="DND 5"),
                SystemAlias(name="D&D 5"),
                SystemAlias(name="D&D 5th Edition"),
                SystemAlias(name="D&D 5th"),
                SystemAlias(name="D&D 5th Ed"),
                SystemAlias(name="D&D 5th Ed."),
                SystemAlias(name="fivee"),
                SystemAlias(name="5th Edition"),
            ],
        ),
        System(
            name="Pathfinder 1e",
            aliases=[
                SystemAlias(name="PF1e"),
                SystemAlias(name="Pathfinder 1st Edition"),
            ],
        ),
        System(
            name="Pathfinder 2e",
            aliases=[
                SystemAlias(name="PF2e"),
                SystemAlias(name="Pathfinder 2nd Edition"),
                SystemAlias(name="Pathfinder"),
            ],
        ),
        System(
            name="Blades in the Dark",
            aliases=[
                SystemAlias(name="BitD"),
                SystemAlias(name="Blades"),
            ],
        ),
        System(
            name="GURPS",
            aliases=[
                SystemAlias(name="Generic Universal RolePlaying System"),
            ],
        ),
        System(
            name="MÖRK BORG",
            aliases=[
                SystemAlias(name="Mork Borg"),
            ],
        ),
        System(
            name="Prismatic",
            aliases=[
                SystemAlias(name="Memories of Stone"),
            ],
        ),
        System(name="The One Ring"),
        System(
            name="Old School Essentials",
            aliases=[
                SystemAlias(name="OSE"),
            ],
        ),
        System(
            name="Dungeon Crawl Classics",
            aliases=[
                SystemAlias(name="DCC"),
            ],
        ),
        System(name="Alien RPG"),
        System(name="Apocalypse World"),
        System(name="Avatar Legends"),
        System(name="Cairn 2e"),
        System(name="Call of Cthulhu 6e"),
        System(name="Call of Cthulhu 7e"),
        System(name="Chronicles of Darkness"),
        System(name="Coriolis: The Third Horizon"),
        System(name="Crash Pandas"),
        System(name="CY_BORG"),
        System(name="Cyberpunk 2020"),
        System(name="Cyberpunk Red"),
        System(name="Daggerheart"),
        System(name="Dark Heresy 1e"),
        System(name="Dark Heresy 2e"),
        System(name="DC20"),
        System(name="Delta Green"),
        System(name="Dread"),
        System(name="Dungeon World"),
        System(name="Eat the Reich"),
        System(name="Electric Bastionland"),
        System(name="Everyone is John"),
        System(name="Fate Accelerated"),
        System(name="Fate Core"),
        System(name="Fiasco"),
        System(name="For the Queen"),
        System(name="Freeform Narrative"),
        System(name="Genesys"),
        System(name="Goblin Quest"),
        System(name="Heart: The City Beneath"),
        System(name="Honey Heist"),
        System(name="Into the Odd"),
        System(name="Kids on Bikes"),
        System(name="Kids on Brooms"),
        System(name="Kingdom"),
        System(name="Lancer"),
        System(name="Legend of the Five Rings"),
        System(name="Mage: the Ascension"),
        System(name="Masks"),
        System(name="Microscope"),
        System(name="Monster of the Week"),
        System(name="Monsterhearts"),
        System(name="Mothership 1e"),
        System(name="Mothership 2e"),
        System(name="Mouse Guard"),
        System(name="Mutants & Masterminds"),
        System(name="Night's Black Agents"),
        System(name="Numenera"),
        System(name="Ozymandias"),
        System(name="Paranoia"),
        System(name="Pendragon"),
        System(name="Powered by the Apocalypse"),
        System(name="Public Access"),
        System(name="Pulp Cthulhu"),
        System(name="Rogue Trader"),
        System(name="Rolemaster"),
        System(name="ROOT RPG"),
        System(name="Savage Worlds"),
        System(name="Shadow of the Demon Lord"),
        System(name="Shadowrun 5e"),
        System(name="Shadowrun 6e"),
        System(name="Spire: The City Must Fall"),
        System(name="Star Wars: Edge of the Empire"),
        System(name="Starfinder 1e"),
        System(name="Starfinder 2e"),
        System(name="Stars Without Number"),
        System(name="Strange Squad"),
        System(name="Surrealpunk"),
        System(name="Tales from the Loop"),
        System(name="Tales of Steam and Sorcery"),
        System(name="Ten Candles"),
        System(name="The Burning Wheel"),
        System(name="The Dark Eye"),
        System(name="The Dresden Files RPG"),
        System(name="The Quiet Year"),
        System(name="The Sprawl"),
        System(name="The Veil"),
        System(name="Things from the Flood"),
        System(name="Trail of Cthulhu"),
        System(name="Traveller"),
        System(name="Triangle Agency"),
        System(name="Trophy Dark"),
        System(name="Trophy Gold"),
        System(name="Unknown Armies"),
        System(name="Urban Shadows"),
        System(name="Vaesen"),
        System(name="Vampire: the Masquerade"),
        System(name="Wanderhome"),
        System(name="Warhammer Fantasy Roleplay 4e"),
        System(name="Wicked Ones"),
        System(name="World of Darkness"),
        System(name="Worlds Without Number"),
    ]

    for system in systems:
        system.submission_status = SubmissionStatus.APPROVED

    content_warnings = [
        # Suggested content warnings
        ContentWarning(name="Abuse", suggested=True),
        ContentWarning(name="Alcohol Use", suggested=True),
        ContentWarning(name="Bigotry or Exclusion", suggested=True),
        ContentWarning(name="Body Horror", suggested=True),
        ContentWarning(name="Death", suggested=True),
        ContentWarning(name="Drug Use", suggested=True),
        ContentWarning(name="Loss of Control or Agency", suggested=True),
        ContentWarning(name="Mental Health", suggested=True),
        ContentWarning(name="Sexual Themes", suggested=True),
        ContentWarning(name="Violence", suggested=True),
        # Other content warnings
        ContentWarning(name="Drowning"),
        ContentWarning(name="Grief"),
        ContentWarning(name="Manipulation"),
        ContentWarning(name="Self-Harm"),
        ContentWarning(name="Spiders"),
        ContentWarning(name="Suffocation"),
        ContentWarning(name="Suicide"),
        ContentWarning(name="Religion"),
    ]

    for content_warning in content_warnings:
        content_warning.submission_status = SubmissionStatus.APPROVED

    transaction.add(event)
    transaction.add_all(genres)
    transaction.add_all(systems)
    transaction.add_all(content_warnings)
