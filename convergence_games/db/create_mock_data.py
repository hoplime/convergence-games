import datetime as dt
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from convergence_games.db.enums import (
    GameActivityRequirement,
    GameClassification,
    GameCrunch,
    GameEquipmentRequirement,
    GameKSP,
    GameNarrativism,
    GameRoomRequirement,
    GameTableSizeRequirement,
    GameTone,
    SubmissionStatus,
)
from convergence_games.db.models import (
    ContentWarning,
    Event,
    Game,
    GameContentWarningLink,
    GameGenreLink,
    GameRequirement,
    GameRequirementTimeSlotLink,
    Genre,
    Room,
    System,
    SystemAlias,
    Table,
    TimeSlot,
    User,
)


async def create_mock_data(transaction: AsyncSession) -> None:
    NZT = ZoneInfo("Pacific/Auckland")  # noqa: N806

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
        Genre(name="Fantasy", submission_status=SubmissionStatus.APPROVED, suggested=True),
        Genre(name="Sci-Fi", submission_status=SubmissionStatus.APPROVED, suggested=True),
        Genre(name="Horror", submission_status=SubmissionStatus.APPROVED, suggested=True),
        Genre(name="Mystery", submission_status=SubmissionStatus.APPROVED, suggested=True),
        Genre(name="Superhero", submission_status=SubmissionStatus.APPROVED, suggested=True),
        Genre(name="Historical", submission_status=SubmissionStatus.APPROVED, suggested=True),
        Genre(name="Post-Apocalyptic", submission_status=SubmissionStatus.APPROVED, suggested=True),
        Genre(name="Cyberpunk", submission_status=SubmissionStatus.APPROVED, suggested=True),
        Genre(name="Steampunk", submission_status=SubmissionStatus.APPROVED, suggested=True),
        Genre(name="Western", submission_status=SubmissionStatus.APPROVED, suggested=True),
        Genre(name="Modern", submission_status=SubmissionStatus.APPROVED, suggested=True),
        Genre(name="Urban Fantasy", submission_status=SubmissionStatus.APPROVED, suggested=True),
        Genre(name="Space Opera", submission_status=SubmissionStatus.APPROVED, suggested=True),
        Genre(name="Pulp", submission_status=SubmissionStatus.APPROVED, suggested=True),
        Genre(name="Sword & Sorcery", submission_status=SubmissionStatus.APPROVED, suggested=True),
        Genre(name="Grimdark", submission_status=SubmissionStatus.APPROVED, suggested=True),
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
            submission_status=SubmissionStatus.APPROVED,
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
            submission_status=SubmissionStatus.APPROVED,
        ),
        System(
            name="Pathfinder 1e",
            aliases=[
                SystemAlias(name="PF1e"),
                SystemAlias(name="Pathfinder 1st Edition"),
            ],
            submission_status=SubmissionStatus.APPROVED,
        ),
        System(
            name="Pathfinder 2e",
            aliases=[
                SystemAlias(name="PF2e"),
                SystemAlias(name="Pathfinder 2nd Edition"),
                SystemAlias(name="Pathfinder"),
            ],
            submission_status=SubmissionStatus.APPROVED,
        ),
        System(
            name="Starfinder 1e",
            submission_status=SubmissionStatus.APPROVED,
        ),
        System(
            name="Starfinder 2e",
            submission_status=SubmissionStatus.APPROVED,
        ),
        System(
            name="Shadowrun 5e",
            submission_status=SubmissionStatus.APPROVED,
        ),
        System(
            name="Shadowrun 6e",
            submission_status=SubmissionStatus.APPROVED,
        ),
        System(
            name="Cyberpunk 2020",
            submission_status=SubmissionStatus.APPROVED,
        ),
        System(
            name="Cyberpunk Red",
            submission_status=SubmissionStatus.APPROVED,
        ),
        System(
            name="Call of Cthulhu 7e",
            submission_status=SubmissionStatus.APPROVED,
        ),
        System(
            name="Call of Cthulhu 6e",
            submission_status=SubmissionStatus.APPROVED,
        ),
        System(
            name="Tales from the Loop",
            submission_status=SubmissionStatus.APPROVED,
        ),
        System(
            name="Kids on Bikes",
            submission_status=SubmissionStatus.APPROVED,
        ),
        System(
            name="Blades in the Dark",
            submission_status=SubmissionStatus.APPROVED,
        ),
        System(
            name="Savage Worlds",
            submission_status=SubmissionStatus.APPROVED,
        ),
        System(
            name="GURPS",
            submission_status=SubmissionStatus.APPROVED,
        ),
        System(
            name="World of Darkness",
            submission_status=SubmissionStatus.APPROVED,
        ),
        System(
            name="Chronicles of Darkness",
            submission_status=SubmissionStatus.APPROVED,
        ),
        System(
            name="Legend of the Five Rings",
            submission_status=SubmissionStatus.APPROVED,
        ),
        System(
            name="Lancer",
            submission_status=SubmissionStatus.APPROVED,
        ),
        System(
            name="Mutants & Masterminds",
            submission_status=SubmissionStatus.APPROVED,
        ),
        System(
            name="Fiasco",
            submission_status=SubmissionStatus.APPROVED,
        ),
        System(
            name="Dread",
            submission_status=SubmissionStatus.APPROVED,
        ),
        System(
            name="Honey Heist",
            submission_status=SubmissionStatus.APPROVED,
        ),
        System(
            name="Monster of the Week",
            submission_status=SubmissionStatus.APPROVED,
        ),
        System(
            name="Powered by the Apocalypse",
            submission_status=SubmissionStatus.APPROVED,
        ),
        System(
            name="The Sprawl",
            submission_status=SubmissionStatus.APPROVED,
        ),
        System(
            name="Apocalypse World",
            submission_status=SubmissionStatus.APPROVED,
        ),
        System(
            name="Monsterhearts",
            submission_status=SubmissionStatus.APPROVED,
        ),
        System(
            name="Dungeon World",
            submission_status=SubmissionStatus.APPROVED,
        ),
        System(
            name="Masks",
            submission_status=SubmissionStatus.APPROVED,
        ),
        System(
            name="Urban Shadows",
            submission_status=SubmissionStatus.APPROVED,
        ),
        System(
            name="The Veil",
            submission_status=SubmissionStatus.APPROVED,
        ),
        System(
            name="The Quiet Year",
            submission_status=SubmissionStatus.APPROVED,
        ),
        System(
            name="Microscope",
            submission_status=SubmissionStatus.APPROVED,
        ),
        System(
            name="Kingdom",
            submission_status=SubmissionStatus.APPROVED,
        ),
        System(
            name="For the Queen",
            submission_status=SubmissionStatus.APPROVED,
        ),
        System(
            name="Mork Borg",
            submission_status=SubmissionStatus.APPROVED,
        ),
        System(
            name="Alien RPG",
            submission_status=SubmissionStatus.APPROVED,
        ),
        System(
            name="Vampire the Masquerade 5e",
            submission_status=SubmissionStatus.APPROVED,
        ),
        System(
            name="Paranoia",
            submission_status=SubmissionStatus.APPROVED,
        ),
        System(
            name="Fate Core",
            submission_status=SubmissionStatus.APPROVED,
        ),
        System(
            name="Warhammer Fantasy Roleplay 4e",
            submission_status=SubmissionStatus.APPROVED,
        ),
    ]

    content_warnings = [
        ContentWarning(name="Violence", suggested=True, submission_status=SubmissionStatus.APPROVED),
        ContentWarning(name="Sexual Themes", suggested=True, submission_status=SubmissionStatus.APPROVED),
        ContentWarning(name="Drug Use", suggested=True, submission_status=SubmissionStatus.APPROVED),
        ContentWarning(name="Alcohol Use", suggested=True, submission_status=SubmissionStatus.APPROVED),
        ContentWarning(name="Mental Health", suggested=True, submission_status=SubmissionStatus.APPROVED),
        ContentWarning(name="Body Horror", suggested=True, submission_status=SubmissionStatus.APPROVED),
        ContentWarning(name="Bigotry", suggested=True, submission_status=SubmissionStatus.APPROVED),
        ContentWarning(name="Death", suggested=True, submission_status=SubmissionStatus.APPROVED),
        ContentWarning(name="Abuse", suggested=True, submission_status=SubmissionStatus.APPROVED),
    ]

    game = Game(
        name="Test Game",
        tagline="This is a test game",
        description="This is a test game description",
        classification=GameClassification.R18,
        crunch=GameCrunch.MEDIUM,
        narrativism=GameNarrativism.NARRATIVIST,
        tone=GameTone.LIGHT_HEARTED,
        player_count_minimum=3,
        player_count_optimum=4,
        player_count_maximum=6,
        ksps=GameKSP.FOR_SALE | GameKSP.DESIGNER_RUN,
        system=systems[0],
        gamemaster=User(
            first_name="John",
            last_name="Cena",
            description="",
        ),
        event=event,
        game_requirement=GameRequirement(
            times_to_run=2,
            table_size_requirement=GameTableSizeRequirement.LARGE,
            equipment_requirement=GameEquipmentRequirement.EXTRA_SIDETABLE,
            activity_requirement=GameActivityRequirement.NONE,
            room_requirement=GameRoomRequirement.NEAR_ANOTHER_TABLE | GameRoomRequirement.QUIET,
            room_notes="This game requires a quiet room near another table",
        ),
        sessions=[],
        submission_status=SubmissionStatus.APPROVED,
    )

    extra_links = [
        GameGenreLink(game=game, genre=genres[0]),
        GameGenreLink(game=game, genre=genres[1]),
        GameContentWarningLink(game=game, content_warning=content_warnings[0]),
        GameContentWarningLink(game=game, content_warning=content_warnings[1]),
        GameRequirementTimeSlotLink(game_requirement=game.game_requirement, time_slot=event.time_slots[0]),
        GameRequirementTimeSlotLink(game_requirement=game.game_requirement, time_slot=event.time_slots[1]),
    ]

    transaction.add(event)
    transaction.add_all(genres)
    transaction.add_all(systems)
    transaction.add_all(content_warnings)
    transaction.add(game)
    transaction.add_all(extra_links)
