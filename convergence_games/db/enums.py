import enum
from abc import ABC
from typing import ClassVar


class GameCrunch(enum.StrEnum):
    LIGHT = "Light"
    MEDIUM = "Medium"
    HEAVY = "Heavy"


class GameNarrativism(enum.StrEnum):
    NARRATIVIST = "Narrativist"
    BALANCED = "Balanced"
    GAMEIST = "Gameist"


class GameTone(enum.StrEnum):
    GOOFY = "Goofy"
    LIGHT_HEARTED = "Light-hearted"
    SERIOUS = "Serious"
    DARK = "Dark"


class GameStatus(enum.StrEnum):
    DRAFT = "Draft"
    SUBMITTED = "Submitted"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    CANCELLED = "Cancelled"


class FlagWithNotes(enum.IntFlag):
    _ignore_ = ["__notes__"]
    __notes__: ClassVar[dict[int, str]] = {}

    @classmethod
    def all_notes_and_values(cls) -> list[tuple[int, str]]:
        return [(member.value, cls.note_for(member.value)) for member in cls]

    @classmethod
    def note_for(cls, value: int) -> str:
        return cls.__notes__.get(value, "")

    @property
    def notes(self) -> list[str]:
        return [self.note_for(value) for value in self]


class GameTableSizeRequirement(FlagWithNotes):
    NONE = 0
    SMALL = 1
    LARGE = 2

    __notes__ = {
        SMALL: "Small table",
        LARGE: "Large table",
    }


class GameEquipmentRequirement(FlagWithNotes):
    NONE = 0
    POWER_OUTLET = 1
    WHITEBOARD = 2
    EXTRA_SIDETABLE = 4
    BULKY_EQUIPMENT = 8
    WIFI_OR_CELL_SERVICE = 16

    __notes__ = {
        POWER_OUTLET: "Power outlet",
        WHITEBOARD: "Whiteboard",
        EXTRA_SIDETABLE: "Extra side table",
        BULKY_EQUIPMENT: "Bulky equipment",
        WIFI_OR_CELL_SERVICE: "WiFi or cell service",
    }


class GameActivityRequirement(FlagWithNotes):
    NONE = 0
    NOISY = 1
    MOVE_BETWEEN_TABLES = 2
    MOVE_AWAY_FROM_VENUE = 4

    __notes__ = {
        NOISY: "Noisy",
        MOVE_BETWEEN_TABLES: "Move between tables",
        MOVE_AWAY_FROM_VENUE: "Move away from venue",
    }


class GameRoomRequirement(FlagWithNotes):
    NONE = 0
    QUIET = 1
    PRIVATE = 2
    NEAR_ANOTHER_TABLE = 4

    __notes__ = {
        QUIET: "Quiet",
        PRIVATE: "Private",
        NEAR_ANOTHER_TABLE: "Near another table",
    }


class Role(enum.StrEnum):
    OWNER = "Owner"  # Can do anything a Manager can do, and assign roles to other users
    MANAGER = "Manager"  # Can manage everything in an event
    READER = "Reader"  # Can read everything in an event
    PLAYER = "Player"  # Is participating in an event - can read and update their own data - the lowest permission


class LoginProvider(enum.StrEnum):
    GOOGLE = "google"
    DISCORD = "discord"
    FACEBOOK = "facebook"
