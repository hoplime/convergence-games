from functools import lru_cache
from typing import TYPE_CHECKING, NewType, cast, overload

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

_sqids = Sqids(alphabet=SETTINGS.SQIDS_ALPHABET or DEFAULT_ALPHABET, min_length=SETTINGS.SQIDS_MIN_LENGTH)

Sqid = NewType("Sqid", str)


@lru_cache
def _ink(class_name: str) -> int:
    """
    Get the ink for a class.
    """
    return hash(class_name) % 100


def sink(sqid: Sqid) -> int:
    """
    Extract the ID from a sqid.
    Suitable to dive into the database!
    """
    return _sqids.decode(sqid)[-1]


@overload
def swim(obj: HasID) -> Sqid: ...


@overload
def swim(obj: str, obj_id: int) -> Sqid: ...


def swim(obj: HasID | str, obj_id: int | None = None) -> Sqid:
    """
    Create a sqid from an object.
    Suitable to surface to the client!
    """
    if isinstance(obj, str):
        class_name = obj
        assert obj_id is not None
    else:
        class_name = obj.__class__.__name__
        obj_id = cast(int, obj.id)

    return cast(Sqid, _sqids.encode([_ink(class_name), obj_id]))


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

    # Length test
    for i in range(10):
        x = 10**i
        sqid = _sqids.encode([0, x])
        print(f"{i}\t{x}\t{sqid}")
