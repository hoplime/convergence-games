# Python Code Style Conventions

## Tooling

- **Package manager**: uv (not pip/poetry). Use `uv run` to execute commands, `uv sync` for dependencies.
- **Linter/formatter**: ruff. Line length 120. See `pyproject.toml [tool.ruff]` for enabled rules.
- **Type checker**: basedpyright. Run with `uv run basedpyright`.
- **Testing**: pytest. Run with `uv run pytest`.

## Naming

- **Files**: `snake_case.py`. Controller files named after their route (e.g., `event_manager.py`).
- **Classes**: `PascalCase`. Pattern `{Entity}{Type}` (e.g., `EventManagerController`, `AlertError`).
- **Request models**: `{Verb}{Entity}Form` or `{Verb}{Entity}Data` (e.g., `PostEmailSignInForm`, `RatingPutData`).
- **Functions/methods**: `snake_case`. Private methods prefixed with single underscore.
- **Constants**: `UPPER_SNAKE_CASE`.
- **Type aliases**: `PascalCase` (e.g., `SessionID`, `PartyLeaderID`).

## Imports

Order (enforced by ruff isort):
1. Standard library (`import datetime as dt`, `from pathlib import Path`)
2. Third-party (`litestar`, `sqlalchemy`, `pydantic`, etc.)
3. Local (`from convergence_games.…`)

Common alias: `import datetime as dt`.

## String Formatting

- Always use f-strings. No `.format()` or `%` formatting.

## Path Handling

- Use `pathlib.Path`, not `os.path`.

## Exports

- Use `__all__` in package `__init__.py` files to define public API.

## Logging

- Logging is not yet formally set up. When it is, it will use a library (likely loguru). For now, `print()` and `rich.pretty.pprint()` are acceptable for local debugging.

## Scripts

- Use `argparse` for CLI argument parsing in scripts (not raw `sys.argv`).

## Async

- All route handlers and database operations are `async def`.
- Use `AsyncGenerator` from `collections.abc` for async context manager yields.
