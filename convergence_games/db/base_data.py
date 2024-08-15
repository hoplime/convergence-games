import datetime as dt

from convergence_games.db.models import Table, TimeSlot

BASE_TIME_SLOTS = [
    TimeSlot(
        id=1,
        name="Saturday Morning",
        start_time=dt.datetime(2024, 9, 7, 9),
        end_time=dt.datetime(2024, 9, 7, 12),
    ),
    TimeSlot(
        id=2,
        name="Saturday Afternoon",
        start_time=dt.datetime(2024, 9, 7, 13),
        end_time=dt.datetime(2024, 9, 7, 16),
    ),
    TimeSlot(
        id=3,
        name="Saturday Evening",
        start_time=dt.datetime(2024, 9, 7, 17),
        end_time=dt.datetime(2024, 9, 7, 21),
    ),
    TimeSlot(
        id=4,
        name="Sunday Morning",
        start_time=dt.datetime(2024, 9, 8, 9),
        end_time=dt.datetime(2024, 9, 8, 12),
    ),
    TimeSlot(
        id=5,
        name="Sunday Afternoon",
        start_time=dt.datetime(2024, 9, 8, 13),
        end_time=dt.datetime(2024, 9, 8, 16),
    ),
]

ROOM_S = "Sigil"
ROOM_1 = "Room 1"
ROOM_2 = "Room 2"
ROOM_3 = "Room 3"
ROOM_4 = "Room 4"
SIDE_1 = "Side 1"
SIDE_2 = "Side 2"
SIDE_3 = "Side 3"
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
    Table(number=26, room=SIDE_1, private=True, id=26),
    Table(number=27, room=SIDE_1, private=True, id=27),
    # Backup Rooms
    Table(number=28, room=EXTRA_, private=False, id=28),
    Table(number=29, room=EXTRA_, private=False, id=29),
    Table(number=30, room=EXTRA_, private=False, id=30),
    # Special Rooms - Multitable
    Table(number=0, room=MULTI_, private=False, id=100),
    # Special Rooms - Overflow
    Table(number=0, room=ROOM_S, private=False, id=404),
]

ALL_BASE_DATA = [
    *BASE_TIME_SLOTS,
    *BASE_TABLES,
]
