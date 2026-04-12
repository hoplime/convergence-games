---
title: Create mock Convergence 2026 event script
created: 2026-04-12
status: complete
---

# Create mock Convergence 2026 event script

## Context

Local development needs a realistic event to work against. Currently the only option is importing the full 2025 production fixture data via `scripts/import_fixtures.py`, which carries user data and games that aren't always appropriate for dev work. A lightweight script that creates just the structural skeleton — event, rooms, tables, time slots — provides a clean starting point that tests and manual dev workflows can build on independently.

## Requirements

- Script at `scripts/create_mock_event.py`, runnable via `PYTHONPATH=. uv run python scripts/create_mock_event.py`
- Creates a "Convergence 2026" event with dates Sep 12–13 2026, timezone `Pacific/Auckland`
- Creates 11 rooms mirroring the 2025 layout (same names, descriptions, facilities)
- Creates 35 tables mirroring the 2025 layout (same numbering, sizes, facilities, room assignments)
- Creates 5 time slots mirroring the 2025 schedule structure (same names, durations), shifted to Sep 2026 dates
- Idempotent: if an event named "Convergence 2026" already exists, skip all creation and report the existing event ID
- Prints suggested `.env` changes (`DEFAULT_EVENT_ID`, `SITE_TITLE`) for the user to apply manually
- Passes `uv run ruff check` and `uv run basedpyright`

## Technical Design

### Script structure

The script follows the ORM pattern established in `convergence_games/db/create_mock_data.py`: build ORM model instances with nested relationships and `session.add()` them. The `Table.before_insert` listener (`convergence_games/db/models.py:507`) auto-populates `event_id` from the parent `Room`, so tables don't need explicit `event_id` assignment.

The script creates its own `AsyncSession` from `SETTINGS.DATABASE_URL` (same approach as `scripts/import_fixtures.py` for engine creation, but using `async_sessionmaker` to get ORM support).

### Data definitions

All data is defined inline as ORM model constructors, nested via relationships where possible (rooms on event, tables on rooms, time_slots on event).

**Event**: "Convergence 2026", Sep 12–13 2026 NZST, `max_party_size=3`

**Rooms** (11, from 2025 fixtures):

| Name                | Description              | Facilities       |
| ------------------- | ------------------------ | ---------------- |
| Sigil               | The Central Meeting Room | NONE             |
| Golarian            | Room 1                   | NONE             |
| Eberron             | Room 2                   | NONE             |
| Doskvol             | Room 3                   | NONE             |
| Arkham              | Room 4                   | NONE             |
| The Lonely Mountain | Room 5                   | NONE             |
| Zhodani Consulate   | Side Room 1              | QUIET \| PRIVATE |
| Prospero's Dream    | Side Room 2              | QUIET \| PRIVATE |
| The Solar Basilica  | Side Room 3              | QUIET            |
| Night City          | The Bar                  | NONE             |
| The Vermission      | Hallways and Corridors   | NONE             |

**Tables** (35, nested under rooms): same numbering (01–09 in Golarian, 11–18 in Eberron, 21–28 in Doskvol, 31–36 in Arkham, 41 in Zhodani Consulate, 42 in Prospero's Dream, 43–44 in The Solar Basilica), with matching `TableSize` and `TableFacility` values from the 2025 fixture data.

**Time Slots** (5, shifted to 2026):

| Name               | Start (NZST) | End (NZST)   | Duration |
| ------------------ | ------------ | ------------ | -------- |
| Saturday Morning   | Sep 12 09:00 | Sep 12 12:00 | 3h       |
| Saturday Afternoon | Sep 12 13:30 | Sep 12 16:30 | 3h       |
| Saturday Evening   | Sep 12 18:00 | Sep 12 22:00 | 4h       |
| Sunday Morning     | Sep 13 09:00 | Sep 13 12:00 | 3h       |
| Sunday Afternoon   | Sep 13 14:30 | Sep 13 18:30 | 4h       |

`checkin_open_time` set to 24h before `start_time` for each slot.

### Idempotency

Query for an existing event by name using `select(Event).where(Event.name == "Convergence 2026")`. If found, skip creation and use its ID for the printed suggestion.

### Output

After creating (or finding) the event, print suggested `.env` changes:

```
Suggested .env changes:
  DEFAULT_EVENT_ID=<id>
  SITE_TITLE=Convergence 2026
```

### Key files

- **New**: `scripts/create_mock_event.py`

### Dependencies (already available)

- `convergence_games.db.models` — `Event`, `Room`, `Table`, `TimeSlot` (`convergence_games/db/models.py`)
- `convergence_games.db.enums` — `RoomFacility`, `TableFacility`, `TableSize` (`convergence_games/db/enums.py`)
- `convergence_games.settings` — `SETTINGS` for `DATABASE_URL` (`convergence_games/settings.py`)

## Implementation Plan

### Phase 1: Create the script

- [ ] **Create `scripts/create_mock_event.py`**
  - Define `async def create_mock_event(session: AsyncSession) -> Event` following the pattern in `convergence_games/db/create_mock_data.py`
  - Query for existing "Convergence 2026" event first; if found, return it
  - Build the `Event` with nested `time_slots` and `rooms` (rooms with nested `tables` via the `tables` relationship)
  - `session.add(event)` and `await session.flush()` to get the generated ID
  - Define `async def main()` that creates engine + `async_sessionmaker`, runs `create_mock_event`, prints suggested `.env` changes
  - Use `argparse` with no required args (following `scripts/import_fixtures.py` convention)

#### Phase 1 verification

- [ ] `uv run ruff check scripts/create_mock_event.py` — no errors
- [ ] `uv run ruff format --check scripts/create_mock_event.py` — no changes needed
- [ ] `uv run basedpyright scripts/create_mock_event.py` — no new errors
- [ ] Run: `PYTHONPATH=. uv run python scripts/create_mock_event.py`
  - Event created with correct name and dates
  - 11 rooms created
  - 35 tables created with correct room assignments
  - 5 time slots created with correct times
  - Prints suggested `.env` changes with correct event ID
- [ ] Run again — idempotent: prints "already exists", no duplicate rows

## Acceptance Criteria

- [ ] `uv run ruff check` — no new errors
- [ ] `uv run basedpyright` — no new errors
- [ ] Script creates event + 11 rooms + 35 tables + 5 time slots matching 2025 layout
- [ ] Script is idempotent (second run reports existing event, no duplicate data)
- [ ] Prints suggested `.env` changes with `DEFAULT_EVENT_ID` and `SITE_TITLE`
- [ ] Dev server starts and uses the new event as default after manually applying `.env` changes
