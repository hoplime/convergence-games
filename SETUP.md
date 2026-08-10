# Local Development Setup

Everything you need to develop and test features locally.

## Prerequisites

| Tool                    | Purpose                 | Install                                                                                    |
| ----------------------- | ----------------------- | ------------------------------------------------------------------------------------------ |
| Linux or WSL 2          | Development environment | [WSL docs](https://learn.microsoft.com/en-us/windows/wsl/install)                          |
| uv                      | Python package manager  | [uv docs](https://docs.astral.sh/uv/getting-started/installation/)                         |
| Node.js + npm           | Frontend build tooling  | [fnm](https://github.com/Schniz/fnm) (recommended) or [nvm](https://github.com/nvm-sh/nvm) |
| Docker + Docker Compose | Local PostgreSQL        | [Docker Engine](https://docs.docker.com/engine/install/)                                   |

Optional (for building production images locally):

| Tool          | Purpose                   | Install                           |
| ------------- | ------------------------- | --------------------------------- |
| Docker Buildx | Multi-stage Docker builds | Included with Docker Engine 23.0+ |

## Quick start

```bash
# 1. Clone and enter the repo
git clone <repo-url> && cd convergence-games

# 2. Copy and configure environment
cp .env.template .env
# Edit .env — at minimum, generate SIGNING_KEY and TOKEN_SECRET (commands are in the template)

# 3. Start PostgreSQL
docker compose -f compose.dev.yaml up -d

# 4. Install dependencies
uv sync
npm install

# 5. Activate the virtual environment
source .venv/bin/activate

# 6. Create database tables
python scripts/create_all_app_metadata.py

# 7. Seed the database
python scripts/create_mock_event.py

# 8. Build frontend assets and generate VSCode component hints
npm run build
python scripts/component_hinting_helper.py src/convergence_games/templates/components/ --add-vscode-settings

# 9. Start the dev server
litestar --app convergence_games.server.app:app run --reload
```

The app is now running at http://localhost:8000.

**VSCode users:** Open the project and set the Python interpreter to `.venv/bin/python` (Ctrl+Shift+P → "Python: Select Interpreter" → select the `.venv` entry). This enables IntelliSense, linting, and the debugger for the correct environment.

## Environment configuration

Copy `.env.template` to `.env`. The template has sensible defaults for local development — the only values you **must** generate are:

| Variable       | How to generate                                                                             |
| -------------- | ------------------------------------------------------------------------------------------- |
| `SIGNING_KEY`  | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `TOKEN_SECRET` | `python -c "import secrets; print(secrets.token_hex(32))"`                                  |

OAuth providers (Google, Discord) and email (Brevo) are optional — leave their keys blank to disable those sign-in methods. You can still access the app; you just won't be able to log in via those providers.

See `src/convergence_games/settings.py` for the full settings class and defaults.

## Database

### Start PostgreSQL

```bash
docker compose -f compose.dev.yaml up -d
```

This starts:
- **PostgreSQL 17** on `localhost:5432` (credentials from your `.env`)
- **DbGate** on http://localhost:3000 — a browser-based database GUI

### Create tables

For a **fresh database** (no existing schema), create all tables directly from the SQLAlchemy models:

```bash
python scripts/create_all_app_metadata.py
```

This is the correct approach for local dev setup. Alembic migrations (`database upgrade`) are for incrementally updating an existing database and require a complete migration chain — they're used in production, not for bootstrapping a new local database from scratch.

### Populate with test data

For a minimal working event (rooms, tables, time slots):

```bash
python scripts/create_mock_event.py
```

To import a full database snapshot from fixtures:

```bash
python scripts/import_fixtures.py fixtures/local_db_backup
```

Set `DEFAULT_EVENT_ID` in `.env` to match the event you want to load by default.

### Other database scripts

```bash
# Dump current database to fixture files
python scripts/dump_fixtures.py <name>

# Seed base data (systems, genres, content warnings) — run by create_mock_data
python -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from convergence_games.settings import SETTINGS
from convergence_games.db.create_mock_data import create_mock_data
from convergence_games.db.models import Base

async def seed():
    engine = create_async_engine(SETTINGS.DATABASE_URL.render_as_string(hide_password=False))
    async with async_sessionmaker(engine)() as session:
        await create_mock_data(session)
        await session.commit()

asyncio.run(seed())
"
```

## Running the app

### Option 1: VSCode (recommended)

Open the project in VSCode and press **F5** (or Run → Start Debugging). The "Python: Uvicorn" launch configuration:

1. Builds TypeScript via Vite
2. Starts Tailwind CSS in watch mode (rebuilds on template changes)
3. Launches uvicorn with debugpy attached and `--reload`

You get breakpoints, hot reload, and CSS rebuilds — all in one keystroke.

### Option 2: Manual CLI

Run these in separate terminals (or use a process manager):

```bash
# Terminal 1 — Tailwind CSS (rebuilds on template changes)
npm run tailwind:watch

# Terminal 2 — Dev server with hot reload
# On WSL, set WATCHFILES_FORCE_POLLING=1 for reliable file-change detection
WATCHFILES_FORCE_POLLING=1 litestar --app convergence_games.server.app:app run --reload
```

Build TypeScript whenever you change `.ts` files:

```bash
npm run build:tsc
```

Or build everything (TypeScript + CSS) in one shot:

```bash
npm run build
```

### Option 3: Docker (production-like)

Build and run the full production image locally:

```bash
# Build the image
docker buildx bake

# Run it (reads .env for DATABASE_* and other config)
docker run --rm --env-file .env -p 8000:8000 jcheatley/waikato-rpg-convergence-games:latest
```

Note: The Docker container expects to connect to the database at the host specified in `.env`. If running PostgreSQL via `compose.dev.yaml`, set `DATABASE_HOST=host.docker.internal` (Docker Desktop) or use `--network host` (Linux).

## Linting and type checking

```bash
ruff check                  # Lint Python
ruff format                 # Format Python
basedpyright                # Type check Python
npx tsc --noEmit            # Type check TypeScript
```

All four are expected to pass before merging (modulo pre-existing basedpyright errors tracked in the baseline).

## Tests

```bash
pytest                              # Run all tests
pytest path/to/test.py              # Run a single file
pytest -k "test_name"               # Run a specific test
```

Tests use an in-memory SQLite database — no running PostgreSQL needed. They live in `tests/` mirroring the `src/convergence_games/` structure.

## VSCode extensions

Recommended extensions are listed in `.vscode/extensions.json`. VSCode will prompt you to install them when you open the project. Key ones:

- **Python** + **Debugpy** + **Ruff** — Python editing, debugging, linting/formatting
- **Jinja HTML** — syntax highlighting for `.html.jinja` templates
- **Tailwind CSS IntelliSense** — class autocomplete in templates
- **Prettier** — formatting for Jinja templates
- **HTMX Tags** — attribute autocomplete for HTMX
- **Run on Save** — auto-rebuilds JinjaX component hints when templates change
