"""Slug generation helpers for models that mix in Advanced Alchemy's `SlugKey`.

Slugs are kebab-case identifiers derived from a source field (e.g. an Event's
`name`). They are unique within their scope (table-wide for Event/User; per
event for Game). On collision, a 4-character `[a-z0-9]` suffix is appended.
"""

import random
import string
from typing import Any

from advanced_alchemy.utils.text import slugify
from sqlalchemy import Select, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from convergence_games.db.models import Base

__all__ = ["generate_unique_slug", "maybe_regenerate_slug", "slugify"]

_SUFFIX_LENGTH = 4
_SUFFIX_ALPHABET = string.ascii_lowercase + string.digits


def _random_suffix() -> str:
    return "".join(random.choices(_SUFFIX_ALPHABET, k=_SUFFIX_LENGTH))  # noqa: S311


def _exists_query(
    model: type[Base],
    candidate: str,
    *,
    scope: dict[str, Any] | None,
    exclude_id: int | None,
) -> Select[tuple[bool]]:
    stmt = select(exists().where(model.slug == candidate))  # pyright: ignore[reportAttributeAccessIssue]
    if scope:
        for key, value in scope.items():
            stmt = stmt.where(getattr(model, key) == value)
    if exclude_id is not None:
        stmt = stmt.where(model.id != exclude_id)
    return stmt


async def _slug_exists(
    session: AsyncSession,
    model: type[Base],
    candidate: str,
    *,
    scope: dict[str, Any] | None = None,
    exclude_id: int | None = None,
) -> bool:
    result = await session.execute(_exists_query(model, candidate, scope=scope, exclude_id=exclude_id))
    return bool(result.scalar())


async def generate_unique_slug(
    session: AsyncSession,
    model: type[Base],
    source: str,
    *,
    scope: dict[str, Any] | None = None,
    exclude_id: int | None = None,
    fallback: str = "untitled",
) -> str:
    """Generate a slug that is unique within `model` (and optionally `scope`).

    The base slug is `slugify(source)`, falling back to `fallback` when slugify
    yields an empty string (e.g. a name of "???"). On collision a 4-character
    `[a-z0-9]` suffix is appended; the loop retries until a free slug is found.

    Pass `exclude_id` to ignore a specific row's existing slug — used when
    regenerating an entity's own slug.
    """
    base = slugify(source) or fallback
    candidate = base
    while await _slug_exists(session, model, candidate, scope=scope, exclude_id=exclude_id):
        candidate = f"{base}-{_random_suffix()}"
    return candidate


async def maybe_regenerate_slug(
    session: AsyncSession,
    instance: Base,
    *,
    source: str,
    scope: dict[str, Any] | None = None,
    fallback: str = "untitled",
) -> None:
    """Regenerate `instance.slug` if `source` no longer matches its slug base.

    Short-circuits when the current slug is already aligned with the desired
    base — either an exact match, or `desired_base-xxxx` (i.e. the base plus a
    previously-applied 4-char collision suffix). This prevents churning the
    slug on edits that don't actually change the slugified form.
    """
    desired_base = slugify(source) or fallback
    current: str | None = getattr(instance, "slug", None)
    if current == desired_base:
        return
    suffix_len = 1 + _SUFFIX_LENGTH  # leading hyphen + suffix chars
    if (
        current is not None
        and current.startswith(f"{desired_base}-")
        and len(current) == len(desired_base) + suffix_len
    ):
        return
    instance.slug = await generate_unique_slug(  # pyright: ignore[reportAttributeAccessIssue]
        session,
        type(instance),
        source,
        scope=scope,
        exclude_id=instance.id,
        fallback=fallback,
    )
