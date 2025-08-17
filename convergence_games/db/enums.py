from __future__ import annotations

import enum
import re
from typing import ClassVar, override

camel_case_pattern = re.compile(r"(?<!^)(?=[A-Z])")


class GameCrunch(enum.StrEnum):
    NEARLY_NOTHING = "Nearly nothing"
    LIGHT = "Light"
    MEDIUM = "Medium"
    HEAVY = "Heavy"
    EXTRA_HEAVY = "Extra heavy"

    @property
    def number(self) -> int:
        if self == GameCrunch.NEARLY_NOTHING:
            return 1
        if self == GameCrunch.LIGHT:
            return 2
        if self == GameCrunch.MEDIUM:
            return 3
        if self == GameCrunch.HEAVY:
            return 4
        if self == GameCrunch.EXTRA_HEAVY:
            return 5

        return 0


class GameTone(enum.StrEnum):
    GOOFY = "Goofy"
    LIGHT_HEARTED = "Light-hearted"
    SERIOUS = "Serious"
    DARK = "Dark"


class SubmissionStatus(enum.StrEnum):
    DRAFT = "Draft"
    SUBMITTED = "Submitted"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    CANCELLED = "Cancelled"

    @property
    def color_classes(self) -> str:
        if self == SubmissionStatus.DRAFT:
            return "badge badge-neutral"
        if self == SubmissionStatus.SUBMITTED:
            return "badge badge-warning"
        if self == SubmissionStatus.APPROVED:
            return "badge badge-success"
        if self == SubmissionStatus.REJECTED:
            return "badge badge-error"
        if self == SubmissionStatus.CANCELLED:
            return "badge badge-error"

        return ""

    @property
    def gm_explanation(self) -> str:
        if self == SubmissionStatus.DRAFT:
            return "Moderators have marked your game as needing more info the last time it was checked. Commonly this is a placeholder description, or missing information which we think might be important for your game e.g. content warnings if the description implies them. You should receive an email with more details soon."
        if self == SubmissionStatus.SUBMITTED:
            return "This game has been submitted and is awaiting moderator review."
        if self == SubmissionStatus.APPROVED:
            return "This game has been approved and will run at the event. If you haven't got one already, you should receive an email with more details soon."
        if self == SubmissionStatus.REJECTED:
            return "Moderators have rejected your game based on its content. This is usually because it does not fit the event's content guidelines, or is not suitable for the event. You should receive an email with more details soon."
        if self == SubmissionStatus.CANCELLED:
            return "This game has been marked as cancelled (at your request) and will not be run at the event."

        return ""


class GameClassification(enum.StrEnum):
    # G = "G"
    PG = "PG"
    M = "M"
    # R16 = "R16"
    R18 = "R18"

    @property
    def age_restriction(self) -> int:
        # if self == GameClassification.R16:
        #     return 16
        if self == GameClassification.R18:
            return 18

        return 0


class FlagWithNotes(enum.IntFlag):
    _ignore_ = ["__notes__"]
    __notes__: ClassVar[dict[int, str]] = {}
    __form_notes__: ClassVar[dict[int, str]] = {}
    __tooltips__: ClassVar[dict[int, str]] = {}
    __icons__: ClassVar[dict[int, str]] = {}
    __excluded_from_submission__: ClassVar[int] = 0

    @classmethod
    def all_notes_and_values(cls) -> list[tuple[int, str]]:
        return [(member.value, cls.note_for(member.value)) for member in cls]

    @classmethod
    def note_for(cls, value: int) -> str:
        return cls.__notes__.get(value, "")

    @property
    def notes(self) -> list[str]:
        return [self.note_for(value) for value in self]

    @classmethod
    def all_form_notes_and_values(cls) -> list[tuple[int, str]]:
        return [(member.value, cls.form_note_for(member.value)) for member in cls]

    @classmethod
    def form_note_for(cls, value: int) -> str:
        return cls.__form_notes__.get(value, "")

    @property
    def form_notes(self) -> list[str]:
        return [self.form_note_for(value) for value in self]

    @classmethod
    def all_tooltips_and_values(cls) -> list[tuple[int, str]]:
        return [(member.value, cls.tooltip_for(member.value)) for member in cls]

    @classmethod
    def tooltip_for(cls, value: int) -> str:
        return cls.__tooltips__.get(value, "")

    @property
    def tooltips(self) -> list[str]:
        return [self.tooltip_for(value) for value in self]

    @classmethod
    def all_icons_and_values(cls) -> list[tuple[int, str]]:
        return [(member.value, cls.icon_for(member.value)) for member in cls]

    @classmethod
    def icon_for(cls, value: int) -> str:
        return cls.__icons__.get(value, "")

    @property
    def icons(self) -> list[str]:
        return [self.icon_for(value) for value in self]


class Requirement(FlagWithNotes):
    __criteria__: ClassVar[dict[int, str]] = {}

    @classmethod
    def all_criteria_and_values(cls) -> list[tuple[int, str]]:
        return [(member.value, cls.criteria_for(member.value)) for member in cls]

    @classmethod
    def criteria_for(cls, value: int) -> str:
        return cls.__criteria__.get(value, "")

    @property
    def criteria(self) -> list[str]:
        result = [self.criteria_for(value) for value in self]
        return [criterion for criterion in result if criterion]  # Filter out empty criteria


class Facility(FlagWithNotes):
    @classmethod
    def all_provides_and_values(cls) -> list[tuple[int, str]]:
        return [(member.value, cls.provide_for(member.value)) for member in cls]

    @classmethod
    def provide_for(cls, value: int) -> str:
        instance = cls(value)
        assert instance is not None
        assert instance.name is not None
        kebab_case_class_name = camel_case_pattern.sub("-", cls.__name__.replace("Facility", "")).lower()
        kebab_case_value_name = instance.name.replace("_", "-").lower()
        return f"{kebab_case_class_name}-{kebab_case_value_name}"

    @property
    def provides(self) -> list[str]:
        return [self.provide_for(value) for value in self]


class GameCoreActivity(FlagWithNotes):
    # Core activities
    NONE = 0
    COMBAT = 1
    EXPLORATION = 2
    INVESTIGATION = 4
    MORAL_DILLEMMA = 8
    PUZZLES = 16
    ROLEPLAYING = 32
    ROMANCE = 64
    SOCIAL = 128
    STEALTH = 256
    SURVIVAL = 512

    __notes__ = {
        COMBAT: "Combat",
        EXPLORATION: "Exploration",
        INVESTIGATION: "Investigation",
        MORAL_DILLEMMA: "Moral dilemmas",
        PUZZLES: "Puzzles",
        ROLEPLAYING: "Roleplaying",
        ROMANCE: "Romance",
        SOCIAL: "Social",
        STEALTH: "Stealth",
        SURVIVAL: "Survival",
    }

    __form_notes__ = {
        COMBAT: "Combat / Tactical combat",
        EXPLORATION: "Exploration",
        INVESTIGATION: "Investigation / Mystery Solving",
        MORAL_DILLEMMA: "Moral dilemmas",
        PUZZLES: "Puzzles",
        ROLEPLAYING: "Roleplaying",
        ROMANCE: "Romance",
        SOCIAL: "Social",
        STEALTH: "Stealth / Infiltration",
        SURVIVAL: "Survival",
    }

    __tooltips__ = {
        COMBAT: "Players using weapons / magical abilities to fight will move the story forward, and with tactical decisions and strategy will be important",
        EXPLORATION: "Exploration will be a significant part of the game, with players needing to discover new locations and secrets",
        INVESTIGATION: "Investigation will be a significant part of the game, with players needing to gather clues and solve mysteries",
        MORAL_DILLEMMA: "Moral dilemmas will be a significant part of the game, with players needing to make difficult decisions with no clear right or wrong answer",
        PUZZLES: "Puzzles will be a significant part of the game, with players needing to solve problems to progress",
        ROLEPLAYING: "Talking to NPCs will be the main way to move the story forward, with dialogue and relationships driving the narrative",
        ROMANCE: "Romance will be a significant part of the game, with players needing to navigate relationships and emotions",
        SOCIAL: "Social interaction between players will be a significant part of the game, with players needing to work together and communicate",
        STEALTH: "Stealth will be a significant part of the game, with players needing to avoid detection and move quietly",
        SURVIVAL: "Survival will be a significant part of the game, with players needing to manage resources and stay alive",
    }


class GameKSP(FlagWithNotes):
    # Key Selling Points
    NONE = 0
    DESIGNER_RUN = 1
    NZ_MADE = 2
    IN_PLAYTEST = 4
    FOR_SALE = 8
    SPECIAL_GUEST = 16

    __notes__ = {
        DESIGNER_RUN: "Designer run",
        NZ_MADE: "NZ made",
        IN_PLAYTEST: "In playtest",
        FOR_SALE: "For sale",
        SPECIAL_GUEST: "Special guest",
    }

    __form_notes__ = {
        DESIGNER_RUN: "I am the designer of this system",
        NZ_MADE: "This system was designed in New Zealand",
        IN_PLAYTEST: "This system is in playtest",
        FOR_SALE: "This system or scenario will be for sale at the event",
        SPECIAL_GUEST: "This system is being run by a special guest",
    }

    __tooltips__ = {
        DESIGNER_RUN: "The designer of this system will be running the game",
        NZ_MADE: "This system is made in New Zealand",
        IN_PLAYTEST: "This system is in playtest, and you have the opportunity to help shape it",
        FOR_SALE: "This system or scenario will be for sale at the event",
        SPECIAL_GUEST: "This system is being run by a special guest",
    }

    __icons__ = {
        DESIGNER_RUN: "icon-[game-icons--meeple]",
        NZ_MADE: "icon-[game-icons--kiwi-bird]",
        IN_PLAYTEST: "icon-[mdi--cog]",
        FOR_SALE: "icon-[raphael--dollar]",
        SPECIAL_GUEST: "icon-[material-symbols--star]",
    }

    __excluded_from_submission__ = SPECIAL_GUEST  # Special guest can only be set by the event organisers


class GameTableSizeRequirement(Requirement):
    NONE = 0
    SMALL = 1
    LARGE = 2

    __notes__ = {
        SMALL: "Small table",
        LARGE: "Large table",
    }

    __form_notes__ = {
        SMALL: "Small circular table",
        LARGE: "Large square table",
    }

    __tooltips__ = {
        SMALL: "1.2m diameter circle. Suitable for up to 4 players with smaller battlemaps, or up to 6 players with a character sheet or so",
        LARGE: "1.6m x 1.7m square. If you require large battlemaps, or more than 6 players",
    }

    __icons__ = {
        SMALL: "icon-[material-symbols--circle]",
        LARGE: "icon-[material-symbols--square]",
    }

    __criteria__ = {
        SMALL: "table-size-small",
        LARGE: "table-size-large",
    }


class GameEquipmentRequirement(Requirement):
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

    __form_notes__ = {
        POWER_OUTLET: "Power outlet",
        WHITEBOARD: "Whiteboard",
        EXTRA_SIDETABLE: "Extra side table",
        BULKY_EQUIPMENT: "Bulky equipment",
        WIFI_OR_CELL_SERVICE: "WiFi or cell service",
    }

    __icons__ = {
        POWER_OUTLET: "icon-[ic--baseline-power]",
        WHITEBOARD: "icon-[fluent--whiteboard-24-filled]",
        EXTRA_SIDETABLE: "icon-[ic--baseline-table-bar]",
        BULKY_EQUIPMENT: "icon-[mdi--fridge]",
        WIFI_OR_CELL_SERVICE: "icon-[material-symbols--wifi]",
    }

    __criteria__ = {
        POWER_OUTLET: "table-power-outlet",
        WHITEBOARD: "table-whiteboard",
        EXTRA_SIDETABLE: "table-extra-sidetable",
    }


class GameActivityRequirement(Requirement):
    NONE = 0
    NOISY = 1
    MOVE_BETWEEN_TABLES = 2
    MOVE_AWAY_FROM_VENUE = 4

    __notes__ = {
        NOISY: "Noisy",
        MOVE_BETWEEN_TABLES: "Move between tables",
        MOVE_AWAY_FROM_VENUE: "Move away from venue",
    }

    __form_notes__ = {
        NOISY: "This game may be particularly noisy",
        MOVE_BETWEEN_TABLES: "Players will need to move between tables",
        MOVE_AWAY_FROM_VENUE: "Players will need to move away from the venue/to another space",
    }

    __tooltips__ = {
        NOISY: "e.g. A Jenga tower might clatter every 15 minutes, or a game with a lot of shouting by design",
    }

    __icons__ = {
        NOISY: "icon-[material-symbols--volume-up]",
        MOVE_BETWEEN_TABLES: "icon-[material-symbols--directions-walk]",
        MOVE_AWAY_FROM_VENUE: "icon-[heroicons--map-pin-16-solid]",
    }


class GameRoomRequirement(Requirement):
    NONE = 0
    QUIET = 1
    PRIVATE = 2
    NEAR_ANOTHER_TABLE = 4

    __notes__ = {
        QUIET: "Quiet",
        PRIVATE: "Private",
        NEAR_ANOTHER_TABLE: "Near another table",
    }

    __form_notes__ = {
        QUIET: "This game requires a quiet room",
        PRIVATE: "This game requires a private room",
        NEAR_ANOTHER_TABLE: "This game requires a room near another table (please specify)",
    }

    __tooltips__ = {
        QUIET: "Note that we have limited private/quiet rooms available, so be mindful this may require some flexibility",
        PRIVATE: "Note that we have limited private/quiet rooms available, so be mindful this may require some flexibility",
    }

    __icons__ = {
        QUIET: "icon-[healthicons--deaf-outline-24px]",
        PRIVATE: "icon-[material-symbols--lock]",
        NEAR_ANOTHER_TABLE: "icon-[material-symbols--near-me]",
    }

    __criteria__ = {
        QUIET: "room-quiet",
        PRIVATE: "room-private",
    }


class RoomFacility(Facility):
    NONE = 0
    QUIET = 1
    PRIVATE = 2

    __icons__ = {
        QUIET: "icon-[healthicons--deaf-outline-24px]",
        PRIVATE: "icon-[material-symbols--lock]",
    }

    __notes__ = {
        QUIET: "Quiet",
        PRIVATE: "Private",
    }


class TableFacility(Facility):
    NONE = 0
    POWER_OUTLET = 1
    WHITEBOARD = 2
    EXTRA_SIDETABLE = 4

    __icons__ = {
        POWER_OUTLET: "icon-[ic--baseline-power]",
        WHITEBOARD: "icon-[fluent--whiteboard-24-filled]",
        EXTRA_SIDETABLE: "icon-[ic--baseline-table-bar]",
    }

    __notes__ = {
        POWER_OUTLET: "Has a power outlet",
        WHITEBOARD: "Has a whiteboard",
        EXTRA_SIDETABLE: "Has an extra side table",
    }


class TableSize(enum.StrEnum):
    SMALL = "Small"
    LARGE = "Large"

    @property
    def description(self) -> str:
        if self == TableSize.SMALL:
            return "Round 1200mm diameter."
        if self == TableSize.LARGE:
            return "Square 1600mm x 1800mm."

        return ""

    @property
    def icon(self) -> str:
        if self == TableSize.SMALL:
            return "icon-[material-symbols--circle]"
        if self == TableSize.LARGE:
            return "icon-[material-symbols--square]"

        return ""

    @property
    def provides(self) -> str:
        if self == TableSize.SMALL:
            return "table-size-small"
        if self == TableSize.LARGE:
            return "table-size-large"

        return ""


class Role(enum.StrEnum):
    OWNER = "Owner"  # Can do anything a Manager can do, and assign roles to other users
    MANAGER = "Manager"  # Can manage everything in an event, e.g. approve games
    READER = "Reader"  # Can read everything in an event
    PLAYER = "Player"  # Is participating in an event - can read and update their own data - the lowest permission


class LoginProvider(enum.StrEnum):
    EMAIL = "email"
    GOOGLE = "google"
    DISCORD = "discord"
    FACEBOOK = "facebook"


class UserGamePreferenceValue(enum.IntEnum):
    D0 = 0
    D4 = 4
    D6 = 6
    D8 = 8
    D10 = 10
    D12 = 12
    D20 = 20

    @property
    def display_class(self) -> str:
        common = "w-8 h-8 text-xl relative mask text-gray-800 after:absolute after:top-1/2 after:left-1/2 after:block after:-translate-x-1/2 after:-translate-y-1/2 after:text-center after:align-middle after:leading-none after:font-bold"
        if self == UserGamePreferenceValue.D0:
            return f"{common} bg-gray-400 mask-d0 after:content-['0']"
        if self == UserGamePreferenceValue.D4:
            return f"{common} bg-blue-400 mask-d4 after:content-['4']"
        if self == UserGamePreferenceValue.D6:
            return f"{common} bg-indigo-400 mask-d6 after:content-['6']"
        if self == UserGamePreferenceValue.D8:
            return f"{common} bg-violet-400 mask-d8 after:content-['8']"
        if self == UserGamePreferenceValue.D10:
            return f"{common} bg-red-400 mask-d10 after:content-['10']"
        if self == UserGamePreferenceValue.D12:
            return f"{common} bg-orange-400 mask-d12 after:content-['12']"
        if self == UserGamePreferenceValue.D20:
            return f"{common} bg-yellow-400 mask-d20 after:content-['20']"

        return common


class TierValue(enum.IntEnum):
    AGE_RESTRICTED = -2
    D0 = 0
    D4 = 4
    D6 = 6
    D8 = 8
    D10 = 10
    D12 = 12
    D20 = 20
    GM = 21

    @property
    def display_class(self) -> str:
        common = "w-8 h-8 text-xl relative mask text-gray-800 after:absolute after:top-1/2 after:left-1/2 after:block after:-translate-x-1/2 after:-translate-y-1/2 after:text-center after:align-middle after:leading-none after:font-bold"

        if self in UserGamePreferenceValue:
            return UserGamePreferenceValue(self).display_class

        if self == TierValue.AGE_RESTRICTED:
            return f"{common} bg-red-500 border px-6 rounded-box after:content-['R18']"
        if self == TierValue.GM:
            return f"{common} bg-white border px-6 rounded-box after:content-['GM']"

        return ""
