import enum


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


class Role(enum.StrEnum):
    OWNER = "Owner"  # Can do anything a Manager can do, and assign roles to other users
    MANAGER = "Manager"  # Can manage everything in an event
    READER = "Reader"  # Can read everything in an event
    PLAYER = "Player"  # Is participating in an event - can read and update their own data - the lowest permission


class LoginProvider(enum.StrEnum):
    GOOGLE = "google"
    DISCORD = "discord"
    FACEBOOK = "facebook"
