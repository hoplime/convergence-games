# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Convergence Games is a web application for managing tabletop RPG convention events (specifically for the Waikato Role-Playing Guild's "Convergence" event). It handles game submissions, player preferences, party formation, session scheduling, and automatic game allocation.

Live at: https://convergence.waikatorpg.co.nz

## Tech Stack

- **Backend**: Python 3.13, Litestar framework, SQLAlchemy (async with asyncpg), PostgreSQL
- **Frontend**: Server-rendered Jinja2/JinjaX templates, HTMX for interactivity, TailwindCSS v4 + DaisyUI v5
- **TypeScript**: Vite-bundled UMD library for rich client-side features (TipTap editor, SortableJS)
- **Package management**: uv (Python), npm (Node)
- **Database migrations**: Alembic via Advanced Alchemy

## Development Commands

### Setup
```bash
docker compose -f compose.dev.yaml up -d   # PostgreSQL + DbGate (DB browser on :3000)
uv sync                                      # Python dependencies
npm install                                  # Node dependencies
```

### Running
```bash
uv run litestar --app convergence_games.app:app run --reload  # Dev server (port 8000)
npm run tailwind:watch                       # CSS rebuild on change
npm run build:tsc                            # TypeScript compile + Vite bundle
npm run build                                # Full frontend build (TS + CSS)
```

### Linting & Type Checking
```bash
uv run ruff check                            # Python lint
uv run ruff format                           # Python format
uv run basedpyright                          # Python type checking
npx tsc --noEmit                             # TypeScript type checking
```

### Database Migrations
```bash
uv run litestar --app convergence_games.app:app database upgrade             # Run migrations
uv run litestar --app convergence_games.app:app database make-migrations -m "description"  # Generate migration (uses Advanced Alchemy CLI)
```
Migrations live in `convergence_games/migrations/versions/`. Alembic post-write hooks auto-run ruff on generated files.

### Tests
```bash
uv run pytest                                # Run all tests
uv run pytest path/to/test.py                # Run single test file
uv run pytest -k "test_name"                 # Run specific test
```

## Architecture

### Application Entry Point
`convergence_games/app/app.py` creates the Litestar application. Config modules live in `convergence_games/app/app_config/` (SQLAlchemy plugin, JWT auth, Jinja/JinjaX templates, Sentry, compression, exception handlers).

### Routing
Three router groups in `convergence_games/app/routers/`:
- **`frontend/`** - Server-rendered HTML pages. Each file is a Litestar Controller (e.g., `EventManagerController`, `SubmitGameController`). A `before_request` hook redirects users who haven't completed profile setup.
- **`api/`** - JSON API endpoints. Only active when `DEBUG=True`.
- **`static/`** - Static file serving and favicons.

### Templates (JinjaX)
Templates use JinjaX component syntax. Components in `templates/components/` are reusable UI elements (PascalCase `.html.jinja` files). Pages in `templates/pages/` are full page templates. All JinjaX components automatically receive `request` via a custom passthrough.

Some pages have co-located TypeScript files (e.g., `event_manage_schedule.ts`) that are bundled through the Vite entry at `app/templates/index.ts` -> re-exported via `app/lib/index.ts` into a single UMD `lib.js`.

### Database Models
All SQLAlchemy models are in `convergence_games/db/models.py` with a single `Base` class (extends `BigIntAuditBase` + `UserAuditColumns` for created_by/updated_by tracking). Key domain models:
- **Event** -> has Rooms, Tables, TimeSlots, Games, Sessions
- **Game** -> belongs to Event, System, User (gamemaster); has GameRequirement, Genres, ContentWarnings, Images
- **Session** -> links a Game to a Table and TimeSlot (with cross-event foreign key constraints)
- **Party** -> groups Users for a TimeSlot; members linked via PartyUserLink with a unique leader constraint
- **User** -> has LoginAccounts, UserEventRoles, UserGamePreferences, D20Transactions, CompensationTransactions

Enums in `convergence_games/db/enums.py` use `FlagWithNotes` (IntFlag with metadata dicts for notes, form notes, tooltips, icons) and `Requirement`/`Facility` subclasses for game/room/table requirements matching.

### Sqid Encoding (`db/ocean.py`)
Database IDs are obfuscated in URLs using Sqids. The API uses ocean-themed naming:
- `swim(obj)` / `swim_upper(obj)` - encode an object's ID to a sqid
- `sink(sqid)` / `sink_upper(sqid)` - decode a sqid back to a database ID
- IDs are salted per model class name via `_ink()`.

### Game Allocation Algorithm
`convergence_games/services/algorithm/game_allocator.py` implements the player-to-session allocation. It works with `AlgParty`, `AlgSession`, and `AlgResult` models (in `services/algorithm/models.py`). Players rate games using a dice-based preference system (D4-D20, higher = stronger preference). The allocator builds tier lists from preferences and assigns parties to sessions respecting player counts, compensation, and constraints.

### Permissions
`convergence_games/permissions/` provides `user_has_permission()` used both in route guards and Jinja templates. Roles: Owner > Manager > Reader > Player.

### Image Storage
`convergence_games/services/image/` supports two backends (configured via `IMAGE_STORAGE_MODE`):
- `filesystem` - local disk storage (development)
- `blob` - Azure Blob Storage (production)

### Settings
`convergence_games/settings.py` uses Pydantic Settings loading from `.env`. Feature flags: `FLAG_PREFERENCES`, `FLAG_PLANNER`.

## Key Conventions

- All SQLAlchemy relationships use `lazy="noload"` by default - relationships must be explicitly loaded in queries.
- Cross-event foreign key constraints ensure Games, Tables, TimeSlots, and Sessions within a Session all belong to the same Event (via `foreign_key_constraint_with_event` helper).
- Frontend CSS uses TailwindCSS v4 with `@plugin` syntax (not v3 `@apply`). Icons via `@iconify/tailwind4` with `icon-[set--name]` classes.
- Python conventions are documented in detail in `.claude/rules/python-*.md`.
