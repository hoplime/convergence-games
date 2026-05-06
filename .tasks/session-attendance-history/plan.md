---
title: Session Attendance History
created: 2026-05-06
status: in-progress
---

# Session Attendance History

## Context

A bug in `put_event_manage_schedule` (`convergence_games/app/routers/frontend/event_manager.py:370`) replaces the entire `event.sessions` list on every save. Combined with `cascade="all, delete-orphan"` on the `Event.sessions` relationship (`convergence_games/db/models.py:174`) and `ondelete="CASCADE"` on `Allocation.session_id` (`convergence_games/db/models.py:1007`), this destroys every `Session` row for the event on each save and cascades through to delete every `Allocation` ever recorded against those sessions. This caused real data loss between sessions 2 and 3 — there is no surviving record of which games attendees played in session 2.

A narrower instance of the same anti-pattern exists in `put_event_manage_allocation` (`convergence_games/app/routers/frontend/event_manager.py:1003-1006`), which unconditionally deletes every `Allocation` for a timeslot (committed and uncommitted alike) before re-inserting only the rows present in the form.

Two-pronged fix:

1. **Stop the bleeding.** Make both endpoints diff-based so unchanged rows stay put and only orphaned rows are deleted. Tighten the schema so future code can't silently delete sessions with allocations attached.
2. **Capture the historic fact.** Introduce a new `SessionAttendance` table — an immutable per-event/per-timeslot/per-user record of who played or ran which game — populated when allocations are committed. Even if the schedule and allocations get rewritten later, attendance survives.

The new table is distinct from the existing `UserGamePlayed` (`convergence_games/db/models.py:923`), which is a per-(user, game) row used for the "have you played this before" preference flow and carries no timeslot or event context.

## Requirements

- `put_event_manage_schedule` only deletes `Session` rows whose `(committed, game_id, table_id, time_slot_id)` no longer appears in the submitted schedule. Unchanged sessions retain their primary keys and their `Allocation` rows.
- `put_event_manage_allocation` only deletes `Allocation` rows orphaned by the new submission. Committed allocations are never deleted by an uncommitted draft save.
- `Event.sessions` no longer cascades `delete-orphan`, so an accidental list reassignment raises rather than silently deletes.
- `Allocation.session_id` uses `ondelete="RESTRICT"`, so any future code that tries to delete a `Session` with allocations fails loudly.
- A new `SessionAttendance` table records `(event_id, time_slot_id, game_id, user_id, role, table_id, source_allocation_id, source, recorded_at)` with a unique constraint on `(event_id, time_slot_id, user_id)`.
- Whenever allocations are committed (`data.commit=True` in `put_event_manage_allocation`), `SessionAttendance` rows are upserted for every party member (role `PLAYER`) and the GM of every committed session in the timeslot (role `GAMEMASTER`). Re-committing the same timeslot is idempotent and simply rewrites the rows.
- A data migration backfills `SessionAttendance` from all existing committed `Allocation` rows across all events, with `source = BACKFILL`.
- Tests cover the schedule-save, allocation-save, and attendance-upsert flows so the data-loss class of bug cannot regress.

## Technical Design

### Data model

New model in `convergence_games/db/models.py`:

```python
class SessionAttendance(Base):
    role: Mapped[AttendanceRole] = mapped_column(Enum(AttendanceRole), index=True)
    source: Mapped[AttendanceSource] = mapped_column(Enum(AttendanceSource))
    recorded_at: Mapped[dt.datetime] = mapped_column(server_default=func.now())

    # Foreign keys (durable entities; no FK to volatile Session/Allocation)
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id"), index=True)
    time_slot_id: Mapped[int] = mapped_column(ForeignKey("time_slot.id"), index=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("game.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)
    table_id: Mapped[int | None] = mapped_column(ForeignKey("table.id"))
    # Plain int (no FK) — the Allocation may later be deleted; this is a debugging breadcrumb only.
    source_allocation_id: Mapped[int | None] = mapped_column(default=None)

    # Relationships (lazy="noload")
    event: Mapped[Event] = relationship(foreign_keys=event_id, lazy="noload")
    time_slot: Mapped[TimeSlot] = relationship(foreign_keys=time_slot_id, lazy="noload")
    game: Mapped[Game] = relationship(foreign_keys=game_id, lazy="noload")
    user: Mapped[User] = relationship(foreign_keys=user_id, lazy="noload")
    table: Mapped[Table | None] = relationship(foreign_keys=table_id, lazy="noload")

    __table_args__ = (
        UniqueConstraint("event_id", "time_slot_id", "user_id"),
        # Mirror the cross-event integrity used elsewhere
        foreign_key_constraint_with_event("session_attendance", "time_slot"),
        foreign_key_constraint_with_event("session_attendance", "game"),
    )
```

New enums in `convergence_games/db/enums.py` (alongside existing `StrEnum`s):

```python
class AttendanceRole(enum.StrEnum):
    PLAYER = "Player"
    GAMEMASTER = "Gamemaster"


class AttendanceSource(enum.StrEnum):
    COMMIT = "Commit"
    BACKFILL = "Backfill"
```

Schema changes to existing models in `convergence_games/db/models.py`:

- Line 174: drop `delete-orphan`, keep `cascade="all"` so an `Event.delete()` still cleans up.
  ```python
  sessions: Mapped[list[Session]] = relationship(back_populates="event", lazy="noload", cascade="all")
  ```
- Line 1007: switch `ondelete="CASCADE"` → `ondelete="RESTRICT"` on `Allocation.session_id`.

### Service layer

New module `convergence_games/services/attendance/__init__.py` exposing:

```python
async def sync_attendance_for_timeslot(
    transaction: AsyncSession,
    *,
    time_slot_id: int,
    event_id: int,
    source: AttendanceSource = AttendanceSource.COMMIT,
) -> None:
    """Idempotently rewrite SessionAttendance rows for a single timeslot.

    Reads all committed Allocation rows for the timeslot, expands each party
    leader's party to all members, joins to Session.game.gamemaster_id to tag
    GM rows, and upserts (event_id, time_slot_id, user_id) -> attendance row.
    Removes attendance rows for users no longer present in any committed
    allocation for the slot.
    """
```

The function:
1. Loads `Allocation` rows where `Allocation.committed` is true and `Allocation.session.time_slot_id == time_slot_id`, eagerly loading `session.game` (for `gamemaster_id`), `party_leader`, and the `Party` reachable via `PartyUserLink` for the leader. (Look up via `Party.party_user_links` joined where `is_leader = True`.)
2. Builds the desired set: for each allocation, emit `(user_id, role, game_id, table_id, source_allocation_id)` for every party member (`PLAYER`) and one row for the GM (`GAMEMASTER`) — detected via `allocation.party_leader_id == session.game.gamemaster_id` (party-of-one) so GMs are already covered without a separate join.
3. Computes the diff against existing `SessionAttendance` rows for `(event_id, time_slot_id)` and applies inserts / updates / deletes. Use Postgres `INSERT ... ON CONFLICT (event_id, time_slot_id, user_id) DO UPDATE` for the upsert.
4. Returns `None`; relies on the caller's `transaction` for commit boundary.

Same module also exposes `async def backfill_all_attendance(transaction)` used by the data migration — iterates all timeslots that have committed allocations and calls `sync_attendance_for_timeslot` with `source=BACKFILL`.

### Diff-based controller fixes

`put_event_manage_schedule` (`convergence_games/app/routers/frontend/event_manager.py:333`):

- Build `existing_by_key: dict[tuple[bool, int, int, int], Session]` keyed on `(committed, game_id, table_id, time_slot_id)` from `event.sessions`.
- For each row in `data.sessions`, pop the matching key from `existing_by_key` (reusing the existing `Session`); if not present, `transaction.add(Session(...))`. When `data.commit`, also process the `committed=True` variant.
- Remaining entries in `existing_by_key` whose `committed` flag matches what's being saved are deleted via `await transaction.delete(session)`. Rows in the *other* `committed` set are never touched on this code path.
- Remove the `event.sessions = new_sessions` assignment entirely.

`put_event_manage_allocation` (`convergence_games/app/routers/frontend/event_manager.py:932`):

- Replace the unconditional `delete(Allocation).where(Allocation.session.has(time_slot_id=...))` with a diff:
  - Load existing `Allocation` rows for the timeslot, filter to `committed == data.commit`.
  - Index by `(party_leader_id, session_id)`.
  - For each `data.allocations` row, reuse if present, insert if not.
  - Delete only the leftover existing rows whose key is no longer in the form.
- After the diff is applied, if `data.commit` is true, call `sync_attendance_for_timeslot(transaction, time_slot_id=..., event_id=event.id, source=AttendanceSource.COMMIT)`.

### Migration

Generated via `litestar --app convergence_games.app:app database make-migrations -m "Add session_attendance table and tighten cascades"`. Manual edits expected:

1. `op.create_table("session_attendance", ...)` with FKs and the unique constraint.
2. `op.alter_column` on `allocation.session_id` to change FK behaviour to `RESTRICT` (drop + recreate the FK constraint).
3. Data migration block that backfills attendance — the simplest approach is raw SQL `INSERT INTO session_attendance (...) SELECT ... FROM allocation JOIN session ... WHERE allocation.committed = true` plus the GM row pass. The migration must not import the service module (Alembic migrations should not depend on app code that may evolve), so the upsert SQL is inlined in the migration.

The cascade change on the SQLAlchemy relationship (`delete-orphan` removal) is a Python-only change and does not require Alembic intervention.

### Tests

New tests under `tests/app/routers/frontend/test_event_manager_schedule.py` and `tests/app/routers/frontend/test_event_manager_allocation.py`, plus `tests/services/attendance/test_attendance_sync.py`. Use the existing fixture pattern from `tests/scripts/` if one exists; otherwise establish a minimal in-memory fixture using a Postgres test container (check `tests/conftest.py`).

Required test cases:

- Schedule save with identical payload: `Session.id` values are unchanged after save (assert by collecting IDs before and after).
- Schedule save that moves one session: only the moved session's row is replaced; allocations on unmoved sessions are untouched.
- Schedule commit when `Allocation` rows already exist on a session: those allocations survive the commit.
- Allocation draft save after commit: committed allocation rows are preserved.
- Allocation commit triggers `SessionAttendance` upsert: row count + role tagging verified.
- Allocation re-commit with the same data: idempotent — row count unchanged, no duplicate rows.
- Allocation re-commit with a player removed from a party: the removed user's `SessionAttendance` row is deleted.
- Schema-level: trying to delete a `Session` with allocations raises `IntegrityError` (verifies the `RESTRICT` switch).

## Implementation Plan

### Phase 1: Diff-based schedule save (immediate bug fix)

- [ ] **Rewrite `put_event_manage_schedule`** (`convergence_games/app/routers/frontend/event_manager.py:333-375`)
  - Replace the build-list-then-assign pattern with a key-based diff
  - Key: `(committed, game_id, table_id, time_slot_id)`
  - Reuse existing `Session` rows; insert only new keys; delete only orphans matching the `committed` flag of the current save
  - Remove `event.sessions = new_sessions`
  - Drop the `print(data)` debug line at line 340

- [ ] **Drop `delete-orphan` from `Event.sessions`** (`convergence_games/db/models.py:174`)
  - Change `cascade="all, delete-orphan"` → `cascade="all"`

#### Phase 1 verification

- [ ] `basedpyright` — no new errors
- [ ] `ruff check` — no new errors
- [ ] Manually save the schedule twice with identical payload via the manage-schedule UI; confirm in the DB that `Session.id` and `Session.created_at` are unchanged

### Phase 2: Diff-based allocation save

- [ ] **Rewrite `put_event_manage_allocation`** (`convergence_games/app/routers/frontend/event_manager.py:932-1009`)
  - Replace the blanket `DELETE` + bulk insert with a key-based diff scoped to `committed == data.commit`
  - Key: `(party_leader_id, session_id)`
  - Load existing rows via `select(Allocation).join(Session).where(Session.time_slot_id == ...)`
  - Reuse, insert, and delete-orphan with explicit `await transaction.delete(...)`

#### Phase 2 verification

- [ ] `basedpyright`, `ruff check`
- [ ] Manually: commit allocations for a timeslot, then save an uncommitted draft; confirm committed `Allocation` rows still present in DB

### Phase 3: New attendance model and migration

- [ ] **Add `AttendanceRole` and `AttendanceSource` enums** (`convergence_games/db/enums.py`)
  - Subclass `enum.StrEnum`
  - Values per Technical Design

- [ ] **Add `SessionAttendance` model** (`convergence_games/db/models.py`)
  - Place near `UserGamePlayed` (line 923) for proximity to related history models
  - FKs to `event`, `time_slot`, `game`, `user`, optional `table`
  - `source_allocation_id: Mapped[int | None]` with no FK
  - `UniqueConstraint("event_id", "time_slot_id", "user_id")`
  - `foreign_key_constraint_with_event` for `time_slot` and `game`
  - All relationships `lazy="noload"`

- [ ] **Switch `Allocation.session_id` to `ondelete="RESTRICT"`** (`convergence_games/db/models.py:1007`)

- [ ] **Generate migration**
  - `litestar --app convergence_games.app:app database make-migrations -m "Add session_attendance table and tighten cascades"`
  - Inspect generated file for `create_table("session_attendance", ...)` and the FK alteration on `allocation.session_id`
  - If the FK alteration isn't auto-generated, add `op.drop_constraint(...)` + `op.create_foreign_key(..., ondelete="RESTRICT")` manually

#### Phase 3 verification

- [ ] `basedpyright`, `ruff check`
- [ ] `litestar --app convergence_games.app:app database upgrade` runs cleanly against a fresh dev DB
- [ ] `litestar --app convergence_games.app:app database downgrade base` runs cleanly (rollback works)

### Phase 4: Attendance service

- [ ] **Create service module** (`convergence_games/services/attendance/__init__.py`)
  - `__all__` exporting `sync_attendance_for_timeslot`, `backfill_all_attendance`
  - Use modern type syntax per `.claude/rules/python-types.md`

- [ ] **Implement `sync_attendance_for_timeslot`**
  - Load committed `Allocation` rows joined to `Session` (filter by `time_slot_id`), with `selectinload(Allocation.session).selectinload(Session.game)` and `selectinload(Allocation.party_leader)`, plus party members via `PartyUserLink`
  - Build desired attendance set: for each allocation, emit one row per party member (or just the leader if no party — GMs as party-of-one); role = `GAMEMASTER` when `party_leader_id == session.game.gamemaster_id`, else `PLAYER`
  - Compute diff against existing `SessionAttendance` rows for the timeslot (key on `user_id`)
  - Apply inserts/updates via `INSERT ... ON CONFLICT (event_id, time_slot_id, user_id) DO UPDATE` (use SQLAlchemy's `postgresql.insert`)
  - Apply deletes for users no longer in the committed set

- [ ] **Implement `backfill_all_attendance`**
  - Query distinct `(time_slot_id, event_id)` pairs from `Allocation` joined to `Session` where `Allocation.committed = True`
  - For each, call `sync_attendance_for_timeslot(..., source=AttendanceSource.BACKFILL)`

#### Phase 4 verification

- [ ] `basedpyright`, `ruff check`
- [ ] Unit tests for the service (Phase 6)

### Phase 5: Wire attendance upsert into commit flow

- [ ] **Call service from `put_event_manage_allocation`** (`convergence_games/app/routers/frontend/event_manager.py`)
  - After the diff is applied and `transaction.add_all(...)` runs, if `data.commit` is true, call `await sync_attendance_for_timeslot(transaction, time_slot_id=sink(time_slot_sqid), event_id=event.id, source=AttendanceSource.COMMIT)`
  - Service runs inside the same `transaction` provider so it commits atomically with the allocations

#### Phase 5 verification

- [ ] `basedpyright`, `ruff check`
- [ ] Manually: commit allocations for a timeslot, query `SELECT * FROM session_attendance WHERE time_slot_id = ?`; verify rows for every party member + every GM, with correct `role`

### Phase 6: Backfill migration

- [ ] **Add data migration step to the Phase 3 migration** (`convergence_games/migrations/versions/<timestamp>_add_session_attendance_*.py`)
  - In `upgrade()`, after `create_table`, run an inlined `INSERT INTO session_attendance (event_id, time_slot_id, game_id, user_id, role, table_id, source_allocation_id, source, recorded_at, created_at, updated_at) SELECT ...` joining `allocation` → `session` → `game` → party expansion via `party_user_link`
  - Use raw SQL (not the service) to keep the migration self-contained
  - Handle GM rows as a second `INSERT` filtered by `allocation.party_leader_id = game.gamemaster_id`
  - On `ON CONFLICT (event_id, time_slot_id, user_id) DO NOTHING` so the migration is re-runnable
  - In `downgrade()`, the `drop_table` removes everything — no extra teardown needed

#### Phase 6 verification

- [ ] Apply migration against a copy of production data (or a reasonable seed); `SELECT COUNT(*) FROM session_attendance GROUP BY source` shows backfill rows
- [ ] Spot-check: pick a known committed event/timeslot, verify expected players appear with correct `role`

### Phase 7: Tests

- [ ] **Schedule save tests** (`tests/app/routers/frontend/test_event_manager_schedule.py` — new)
  - Identical-payload save preserves `Session.id`s
  - Single-session move only replaces that session
  - Schedule save preserves `Allocation` rows attached to unchanged sessions
  - Attempting to delete a `Session` with allocations raises `IntegrityError`

- [ ] **Allocation save tests** (`tests/app/routers/frontend/test_event_manager_allocation.py` — new)
  - Uncommitted draft save preserves committed allocations
  - Identical-payload commit is idempotent (no row churn)

- [ ] **Attendance service tests** (`tests/services/attendance/test_attendance_sync.py` — new)
  - Commit creates one `SessionAttendance` row per party member + GM
  - Re-commit with same data is idempotent
  - Re-commit with a player removed deletes that user's row
  - Re-commit with a different game on the same table updates the existing row's `game_id`

#### Phase 7 verification

- [ ] `pytest tests/app/routers/frontend/test_event_manager_schedule.py tests/app/routers/frontend/test_event_manager_allocation.py tests/services/attendance/` passes
- [ ] Full suite: `pytest`

## Acceptance Criteria

- [ ] Type checking passes (`basedpyright`)
- [ ] Linting passes (`ruff check`)
- [ ] Full test suite passes (`pytest`)
- [ ] Migration upgrades and downgrades cleanly on a fresh dev DB
- [ ] Manual: save schedule with identical payload twice → no `Session.id` churn (verify in DbGate)
- [ ] Manual: commit allocations → `session_attendance` populated with correct `role` for players and GMs
- [ ] Manual: re-commit identical allocations → no `session_attendance` row churn
- [ ] Manual: change a single session's game in the schedule, then re-save → only that session's row changes; surrounding allocations and attendance untouched
- [ ] Backfill migration produces a non-zero row count when applied against a DB with existing committed allocations

## Risks and Mitigations

1. **Backfill misses overflow players or no-shows.** Mitigation: backfill only reflects what was committed. Manual reconciliation outside this task. Document in `Notes` so the team knows backfill ≠ ground truth.
2. **`ondelete="RESTRICT"` change breaks an existing flow that relied on cascade-deleting allocations when a session is removed.** Mitigation: the only legitimate delete-session path is now the diff-based schedule save, which only deletes orphans (sessions with no allocations attached, or sessions whose attached allocations the operator explicitly removed first). Run the test suite and a manual smoke before merge. If a flow surfaces, surface the `IntegrityError` to the user with an `AlertError` rather than silently destroying data.
3. **Party member loading is N+1.** Mitigation: in `sync_attendance_for_timeslot` use a single query with `selectinload` for `Allocation.party_leader` and a join through `PartyUserLink` to materialise all members in bulk; verify with SQL echo in dev.
4. **Backfill migration is slow on large prod data.** Mitigation: it's a one-shot raw SQL `INSERT ... SELECT`, not row-by-row. Should be sub-second even for thousands of allocations. If it's not, batch by event.
5. **`SessionAttendance` and committed allocations drift over time.** Mitigation: the service is the only writer in normal operation, and re-runs idempotently on every commit. A future admin "resync" endpoint or scheduled job (out of scope here) can call `sync_attendance_for_timeslot` to reconcile if drift is ever observed.

## Notes

- The existing `UserGamePlayed` model (`convergence_games/db/models.py:923`) is intentionally untouched. It serves a different purpose (have-you-played-this-before flag for preferences) and has no timeslot/event context. Future work could populate it from `SessionAttendance` to remove the manual self-report flow, but that's a separate task.
- Read-side integration (user-facing "your game history" page reading from `SessionAttendance`) is explicitly out of scope. Follow-up task once the table has been populated in production for at least one event.
- The `archived_at` soft-delete column on `Allocation` discussed during design was deliberately deferred. With diff-based saves and `SessionAttendance` capturing the historical fact, the additional planning audit trail isn't worth the partial-unique-index complexity.
- A dedicated admin "lock attendance" action (commit-independent way to capture last-minute manual swaps at the table) was discussed and deferred. Today, attendance == latest commit; if last-minute swaps happen, the operator must commit again.
- Sentry / logging: the service should `print()` (per project convention) when it inserts/deletes attendance rows during commit so any anomalies are visible in dev. Convert to structured logging when the project introduces a logger.
