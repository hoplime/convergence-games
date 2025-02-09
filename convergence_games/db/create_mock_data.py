import datetime as dt
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from convergence_games.db.models import ContentWarning, Event, Genre, Room, System, SystemAlias, Table, TimeSlot


async def create_mock_data(db_session: AsyncSession) -> None:
    NZT = ZoneInfo("Pacific/Auckland")

    event = Event(
        name="Test Event",
        description="This is a test event",
        start_date=dt.datetime(2025, 9, 13, tzinfo=NZT),
        end_date=dt.datetime(2025, 9, 14, tzinfo=NZT),
        rooms=[
            Room(name="Room 1", description="This is room 1", tables=[Table(name="Table 1"), Table(name="Table 2")]),
            Room(name="Room 2", description="This is room 2", tables=[Table(name="Table 3"), Table(name="Table 4")]),
        ],
        time_slots=[
            TimeSlot(
                name="Saturday Morning",
                start_time=dt.datetime(2025, 9, 13, 9, 0, tzinfo=NZT),
                end_time=dt.datetime(2025, 9, 13, 12, 0, tzinfo=NZT),
            ),
            TimeSlot(
                name="Saturday Afternoon",
                start_time=dt.datetime(2025, 9, 13, 13, 0, tzinfo=NZT),
                end_time=dt.datetime(2025, 9, 13, 17, 0, tzinfo=NZT),
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
                start_time=dt.datetime(2025, 9, 14, 13, 0, tzinfo=NZT),
                end_time=dt.datetime(2025, 9, 14, 17, 0, tzinfo=NZT),
            ),
        ],
    )

    genres = [
        Genre(name="Fantasy"),
        Genre(name="Sci-Fi"),
        Genre(name="Horror"),
        Genre(name="Mystery"),
        Genre(name="Superhero"),
        Genre(name="Historical"),
        Genre(name="Post-Apocalyptic"),
        Genre(name="Cyberpunk"),
        Genre(name="Steampunk"),
        Genre(name="Western"),
        Genre(name="Modern"),
        Genre(name="Urban Fantasy"),
        Genre(name="Space Opera"),
        Genre(name="Pulp"),
        Genre(name="Sword & Sorcery"),
        Genre(name="Grimdark"),
    ]

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
        System(name="Starfinder 1e"),
        System(name="Starfinder 2e"),
        System(name="Shadowrun 5e"),
        System(name="Shadowrun 6e"),
        System(name="Cyberpunk 2020"),
        System(name="Cyberpunk Red"),
        System(name="Call of Cthulhu 7e"),
        System(name="Call of Cthulhu 6e"),
        System(name="Tales from the Loop"),
        System(name="Kids on Bikes"),
        System(name="Blades in the Dark"),
        System(name="Savage Worlds"),
        System(name="GURPS"),
        System(name="World of Darkness"),
        System(name="Chronicles of Darkness"),
        System(name="Legend of the Five Rings"),
        System(name="Lancer"),
        System(name="Mutants & Masterminds"),
        System(name="Fiasco"),
        System(name="Dread"),
        System(name="Honey Heist"),
        System(name="Monster of the Week"),
        System(name="Powered by the Apocalypse"),
        System(name="The Sprawl"),
        System(name="Apocalypse World"),
        System(name="Monsterhearts"),
        System(name="Dungeon World"),
        System(name="Masks"),
        System(name="Urban Shadows"),
        System(name="The Veil"),
        System(name="The Quiet Year"),
        System(name="Microscope"),
        System(name="Kingdom"),
        System(name="For the Queen"),
        System(name="Mork Borg"),
        System(name="Alien RPG"),
        System(name="Vampire the Masquerade 5e"),
        System(name="Paranoia"),
        System(name="Fate Core"),
        System(name="Warhammer Fantasy Roleplay 4e"),
    ]

    content_warnings = [
        ContentWarning(name="Violence"),
        ContentWarning(name="Sexual Themes"),
        ContentWarning(name="Drug Use"),
        ContentWarning(name="Alcohol Use"),
        ContentWarning(name="Mental Health"),
        ContentWarning(name="Body Horror"),
        ContentWarning(name="Bigotry"),
        ContentWarning(name="Death"),
        ContentWarning(name="Abuse"),
    ]

    async with db_session as session:
        session.add(event)
        session.add_all(genres)
        session.add_all(systems)
        session.add_all(content_warnings)

        await session.commit()
