from typing import TYPE_CHECKING, cast

from sqids import Sqids
from sqids.constants import DEFAULT_ALPHABET

from convergence_games.settings import SETTINGS

if TYPE_CHECKING:
    from typing import Protocol, TypeAlias

    from sqlalchemy.orm import declared_attr

    class HasIDProperty(Protocol):
        @property
        def id(self) -> int | declared_attr[int]: ...

    class HasIDInstanceAttribute(Protocol):
        id: int | declared_attr[int]

    HasID: TypeAlias = HasIDProperty | HasIDInstanceAttribute
else:
    from typing import Any, TypeAlias

    HasID: TypeAlias = Any

sqids = Sqids(alphabet=SETTINGS.SQIDS_ALPHABET or DEFAULT_ALPHABET)

INKS: dict[str, int] = {
    "AllocationResult": 1,
    "Compensation": 2,
    "ContentWarning": 3,
    "Event": 4,
    "Game": 5,
    "GameContentWarningLink": 6,
    "GameExtraGamemasterLink": 7,
    "GameGenreLink": 8,
    "Genre": 9,
    "Group": 10,
    "GroupSessionPreference": 11,
    "Room": 12,
    "Session": 13,
    "System": 14,
    "Table": 15,
    "TimeSlot": 16,
    "User": 17,
    "UserEventInfo": 18,
    "Venue": 19,
}


def sink(sqid: str) -> int:
    """
    Extract the ID from a sqid.
    Suitable to dive into the database!
    """
    return sqids.decode(sqid)[-1]


def swim(obj: HasID) -> str:
    """
    Create a sqid from an object.
    Suitable to surface to the client!
    """
    return sqids.encode([INKS.get(obj.__class__.__name__, 0), cast(int, obj.id)])


if __name__ == "__main__":
    # Example usage
    from convergence_games.db.models import Genre, System

    genres = [
        Genre(id=1, name="Fantasy", description="Magic and dragons"),
        Genre(id=2, name="Sci-Fi", description="Space and technology"),
        Genre(id=3, name="Horror", description="Spooky and scary"),
    ]

    for genre in genres:
        sqid = swim(genre)
        print(genre.id, sqid, sink(sqid))

    systems = [
        System(id=1, name="D&D 5e", description="Dungeons and Dragons 5th Edition"),
        System(id=2, name="Pathfinder 2e", description="Pathfinder 2nd Edition"),
        System(id=3, name="Cyberpunk 2020", description="Cyberpunk 2020"),
    ]

    for system in systems:
        sqid = swim(system)
        print(system.id, sqid, sink(sqid))
