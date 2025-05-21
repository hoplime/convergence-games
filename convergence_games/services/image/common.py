from typing import Sequence
from uuid import UUID


def subfolder_names_for_guid(lookup: UUID) -> Sequence[str]:
    lookup_str = str(lookup)
    return lookup_str[:2], lookup_str[2:4], lookup_str[4:6]
