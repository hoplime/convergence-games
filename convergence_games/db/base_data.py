import datetime as dt

from convergence_games.db.extra_types import GameTone
from convergence_games.db.models import Game, Person, System, Table, TableAllocation, TimeSlot

# We have to, very boringly, define all of the IDs for the base data.

BASE_TIME_SLOTS = [
    TimeSlot(
        id=1,
        name="Saturday Morning",
        start_time=dt.datetime(2024, 9, 7, 9, 30),
        end_time=dt.datetime(2024, 9, 7, 12, 30),
    ),
    TimeSlot(
        id=2,
        name="Saturday Afternoon",
        start_time=dt.datetime(2024, 9, 7, 13, 30),
        end_time=dt.datetime(2024, 9, 7, 16, 30),
    ),
    TimeSlot(
        id=3,
        name="Saturday Evening",
        start_time=dt.datetime(2024, 9, 7, 18, 0),
        end_time=dt.datetime(2024, 9, 7, 22, 0),
    ),
    TimeSlot(
        id=4,
        name="Sunday Morning",
        start_time=dt.datetime(2024, 9, 8, 9, 15),
        end_time=dt.datetime(2024, 9, 8, 12, 15),
    ),
    TimeSlot(
        id=5,
        name="Sunday Afternoon",
        start_time=dt.datetime(2024, 9, 8, 14, 0),
        end_time=dt.datetime(2024, 9, 8, 18, 0),
    ),
]

ROOM_S = "Sigil"
ROOM_1 = "Room 1 - Vessel Golarian"
ROOM_2 = "Room 2 - Eberron Excavation"
ROOM_3 = "Room 3 - Arkham Station"
ROOM_4 = "Room 4 - USCSS Doskvol"
SIDE_1 = "Side 1 - Rivendell"
SIDE_2 = "Side 2 - The Shire"
SIDE_3 = "Side 3 - Mordor"
EXTRA_ = "Extra Backup"
MULTI_ = "Multitable Meeting Point"

BASE_TABLES = [
    # Room 1
    Table(number=1, room=ROOM_1, private=False, id=1),
    Table(number=2, room=ROOM_1, private=False, id=2),
    Table(number=3, room=ROOM_1, private=False, id=3),
    Table(number=4, room=ROOM_1, private=False, id=4),
    Table(number=5, room=ROOM_1, private=False, id=5),
    Table(number=6, room=ROOM_1, private=False, id=6),
    # Room 2
    Table(number=7, room=ROOM_2, private=False, id=7),
    Table(number=8, room=ROOM_2, private=False, id=8),
    Table(number=9, room=ROOM_2, private=False, id=9),
    Table(number=10, room=ROOM_2, private=False, id=10),
    Table(number=11, room=ROOM_2, private=False, id=11),
    Table(number=12, room=ROOM_2, private=False, id=12),
    # Room 3
    Table(number=13, room=ROOM_3, private=False, id=13),
    Table(number=14, room=ROOM_3, private=False, id=14),
    Table(number=15, room=ROOM_3, private=False, id=15),
    Table(number=16, room=ROOM_3, private=False, id=16),
    Table(number=17, room=ROOM_3, private=False, id=17),
    Table(number=18, room=ROOM_3, private=False, id=18),
    # Room 4
    Table(number=19, room=ROOM_4, private=False, id=19),
    Table(number=20, room=ROOM_4, private=False, id=20),
    Table(number=21, room=ROOM_4, private=False, id=21),
    Table(number=22, room=ROOM_4, private=False, id=22),
    Table(number=23, room=ROOM_4, private=False, id=23),
    Table(number=24, room=ROOM_4, private=False, id=24),
    # Side Rooms
    Table(number=25, room=SIDE_1, private=True, id=25),
    Table(number=26, room=SIDE_2, private=True, id=26),
    Table(number=27, room=SIDE_3, private=True, id=27),
    # Backup Rooms
    Table(number=28, room=EXTRA_, private=False, id=28),
    Table(number=29, room=EXTRA_, private=False, id=29),
    Table(number=30, room=EXTRA_, private=False, id=30),
    # Special Rooms - Multitable
    Table(number=0, room=MULTI_, private=False, id=100),
    # Special Rooms - Overflow
    overflow_table := Table(number=0, room=ROOM_S, private=False, id=404),
]

BASE_PERSONS = [Person(id=0, name="An Amazing Volunteer", email="waikatoroleplayingguild@gmail.com")]

BASE_SYSTEMS = [
    System(
        id=0,
        name="Mystery",
        description="This is a placeholder system for overflow tables.",
    )
]

BASE_OVERFLOW_GAMES = [
    Game(
        id=0,
        title="Overflow",
        description="This is a placeholder game for overflow tables.\nIt looks like all the games you were interested in are too full to fit your group!",
        tone=GameTone.SERIOUS,
        minimum_players=0,
        optimal_players=0,
        maximum_players=1000,
        hidden=True,
        gamemaster_id=BASE_PERSONS[0].id,
        system_id=BASE_SYSTEMS[0].id,
    )
]

BASE_TABLE_ALLOCATIONS = [
    TableAllocation(
        id=time_slot.id,
        table_id=overflow_table.id,
        time_slot_id=time_slot.id,
        game_id=BASE_OVERFLOW_GAMES[0].id,
    )
    for time_slot in BASE_TIME_SLOTS
]

ALL_BASE_DATA = [
    *BASE_TIME_SLOTS,
    *BASE_TABLES,
    *BASE_PERSONS,
    *BASE_SYSTEMS,
    *BASE_OVERFLOW_GAMES,
    *BASE_TABLE_ALLOCATIONS,
]
