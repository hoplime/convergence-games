---
alwaysApply: false
paths: **/*.py
---

# Python Code Style Conventions

## Tooling

- **Package manager**: uv (not pip/poetry). Use `uv sync` for dependencies.
- **Linter/formatter**: ruff. Line length 120. See `pyproject.toml [tool.ruff]` for enabled rules.
- **Type checker**: basedpyright. Run with `basedpyright`.
- **Testing**: pytest. Run with `pytest`.

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

- Use **structlog** for all diagnostic logging in the application. The pipeline is configured in `convergence_games/logging/`.
- At module top: `from convergence_games.logging import get_logger; logger = get_logger(__name__)`. Don't use stdlib `logging` directly in application code — stdlib loggers (uvicorn, SQLAlchemy, etc.) are bridged through the same pipeline already.
- Log calls take an event name as the first positional arg and structured fields as kwargs: `logger.info("game_created", game_id=game.id)`. Don't pass f-strings as event names; the event name is a stable identifier and the kwargs are the data.
- Per-request `request_id`, `method`, `path`, and `user_id` are bound automatically by `LoggingContextMiddleware`. Inside a handler/service/repository, just call `logger.info(...)` and those fields are merged into the record via `structlog.contextvars`.
- Use `from convergence_games.logging import bind, bound` to attach extra fields. Prefer `with bound(event_id=..., action=...): ...` for scoped fields, falling out of context when the block exits. The canonical `http_request` log line at request end carries everything bound during the request.
- Output is environment-aware: `structlog.dev.ConsoleRenderer` (pretty, colored) when `ENVIRONMENT=development` or `DEBUG=true`; `structlog.processors.JSONRenderer` otherwise.
- Sentry receives INFO+ logs as breadcrumbs and ERROR+ logs as issue events automatically; bound contextvars are set on the Sentry scope as tags via `sentry_scope_processor`.
- `print()` and `rich.pretty.pprint()` are reserved for `scripts/` and `__main__` blocks (CLI / human-facing output). They have no place in runtime code paths.

## Scripts

- Use `argparse` for CLI argument parsing in scripts (not raw `sys.argv`).

## Async

- All route handlers and database operations are `async def`.
- Use `AsyncGenerator` from `collections.abc` for async context manager yields.
