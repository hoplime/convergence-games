"""Find users with duplicate emails across login providers.

Scans all UserLogin rows, groups by normalized email, and reports any email
that resolves to more than one User. Also flags multiple UserLogin rows under
a single user where raw casing differs. Does NOT modify any data.

Usage:
    PYTHONPATH=. uv run python scripts/find_duplicate_users.py
    PYTHONPATH=. uv run python scripts/find_duplicate_users.py --verbose
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from convergence_games.db.enums import LoginProvider
from convergence_games.db.models import User, UserLogin
from convergence_games.settings import SETTINGS
from convergence_games.utils.email import normalize_email

type EmailGroup = dict[str, list[tuple[User, UserLogin]]]


async def _load_logins() -> list[UserLogin]:
    engine = create_async_engine(SETTINGS.DATABASE_URL)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        logins = (
            await session.execute(select(UserLogin).options(selectinload(UserLogin.user)))
        ).scalars().all()
    await engine.dispose()
    return list(logins)


def _group_by_email(logins: list[UserLogin]) -> EmailGroup:
    groups: EmailGroup = {}
    for login in logins:
        raw_email = login.provider_email
        if raw_email is None and login.provider == LoginProvider.EMAIL:
            raw_email = login.provider_user_id
        if raw_email is None:
            continue
        key = normalize_email(raw_email)
        groups.setdefault(key, []).append((login.user, login))
    return groups


def _report_cross_user(groups: EmailGroup) -> int:
    print("=== Cross-user duplicates (same email, different users) ===\n")
    count = 0
    for email_key, entries in sorted(groups.items()):
        user_ids = {user.id for user, _ in entries}
        if len(user_ids) <= 1:
            continue
        count += 1
        print(f"  Email: {email_key}")
        for user, login in entries:
            line = (
                f"    User #{user.id} ({user.full_name or '(no name)'}, created {user.created_at})"
                + f"  login: {login.provider.value} / {login.provider_user_id}"
                + f"  raw_email: {login.provider_email}"
            )
            print(line)
        print()
    if count == 0:
        print("  None found.\n")
    return count


def _report_casing_mismatches(groups: EmailGroup) -> int:
    print("=== Intra-user casing mismatches (same user, different raw casing) ===\n")
    user_email_raws: dict[tuple[int, str], set[str]] = {}
    for email_key, entries in groups.items():
        for user, login in entries:
            raw = login.provider_email or login.provider_user_id
            user_email_raws.setdefault((user.id, email_key), set()).add(raw)

    count = 0
    for (user_id, email_key), raws in sorted(user_email_raws.items()):
        if len(raws) <= 1:
            continue
        count += 1
        print(f"  User #{user_id}, email: {email_key}")
        for raw in sorted(raws):
            print(f"    raw: {raw}")
        print()
    if count == 0:
        print("  None found.\n")
    return count


async def find_duplicates(verbose: bool) -> bool:
    logins = await _load_logins()
    groups = _group_by_email(logins)

    cross_user_count = _report_cross_user(groups)
    casing_count = _report_casing_mismatches(groups)

    print(f"Cross-user duplicates: {cross_user_count}")
    print(f"Intra-user casing mismatches: {casing_count}")

    if verbose:
        print(f"\nTotal logins scanned: {len(logins)}")
        print(f"Unique normalized emails: {len(groups)}")

    if cross_user_count or casing_count:
        print("\nAction required: manually reassign or merge duplicate UserLogin rows")
        print("before adding a uniqueness constraint on normalized email.")
        return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Find duplicate users by email across login providers")
    _ = parser.add_argument("--verbose", action="store_true", help="Print additional statistics")
    args = parser.parse_args()

    verbose = bool(args.verbose)
    has_duplicates = asyncio.run(find_duplicates(verbose=verbose))
    sys.exit(1 if has_duplicates else 0)


if __name__ == "__main__":
    main()
