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


DEFINED_CONTENT_WARNINGS = [
    "Extreme Violence",
    "Horror",
    "Bigotry or Exclusion",
    "Manipulation",
    "Drugs",
    "Sexual themes",
]

DEFINED_AGE_SUITABILITIES = [
    "Anyone",
    "Teens (13 ~16)",
    "M (16+)",
    "R (18+)",
]
