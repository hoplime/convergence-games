"""Dump all database tables to JSON fixture files.

Usage:
    PYTHONPATH=. python scripts/dump_fixtures.py <name>

Runs: litestar database dump-data --dir fixtures/<name> --table '*'
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from typing import cast


def main() -> None:
    parser = argparse.ArgumentParser(description="Dump database tables to JSON fixture files.")
    _ = parser.add_argument("name", help="Subdirectory name under fixtures/ (e.g. 'local_db_backup')")
    args = parser.parse_args()
    name = cast(str, args.name)

    cmd = [
        "litestar",
        "--app",
        "convergence_games.app:app",
        "database",
        "dump-data",
        "--dir",
        f"fixtures/{name}",
        "--table",
        "*",
    ]

    print(f"Dumping to fixtures/{name}")
    result = subprocess.run(cmd, check=False)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
