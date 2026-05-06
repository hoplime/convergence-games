---
title: Event time span gating
created: 2026-05-06
status: in-progress
---

# Event Time Span Gating

## Context

Event model has no phase/state controls. Game submission, editing, preferences, and planner are all ungated — available anytime. Only phase control is `TimeSlotStatus` per-timeslot (gates party formation, freezes preferences at allocation). Feature flags `FLAG_PREFERENCES` / `FLAG_PLANNER` exist in settings but are unused.

Goal: add datetime-based windows to Event that auto-enforce when features are available. Matches the `checkin_open_time` pattern already on TimeSlot.

## Requirements

- GMs can only submit new games within a configurable submissions window
- GMs can only edit existing games until a configurable editing deadline
- Players can only set dice preferences after a configurable open date
- Players can only access planner after a configurable open date
- All fields nullable — NULL means backward-compatible defaults (submissions/editing open; preferences/planner closed)
- Admin/owner users bypass all gates
- Existing `checkin_open_time` on TimeSlot enforced in check-in endpoint
- Dead `FLAG_PREFERENCES` / `FLAG_PLANNER` removed from settings
- Game browsing remains always available (no gating)
- Per-timeslot preference freeze at allocation unchanged

## Technical Design

### New Event fields

5 nullable `DateTimeUTC` columns on Event (`convergence_games/db/models.py:128`):
- `submissions_open_at` / `submissions_close_at` — window for new game submissions
- `editing_close_at` — deadline for editing existing games (opens implicitly with submissions)
- `preferences_open_at` — when players can start setting preferences (no close — per-timeslot freeze handles it)
- `planner_open_at` — when players can access schedule planner

### Helper methods on Event

4 `is_*_open(now=None) -> bool` methods. Asymmetric defaults:
- `is_submissions_open`: returns `True` when both fields NULL (backward compat)
- `is_editing_open`: returns `True` when both `submissions_open_at` and `editing_close_at` NULL
- `is_preferences_open`: returns `False` when `preferences_open_at` NULL (must be explicitly opened)
- `is_planner_open`: returns `False` when `planner_open_at` NULL

### Route enforcement

Submit game controller (`convergence_games/app/routers/frontend/submit_game.py`):
- New game POST: `event.is_submissions_open()` check, raise `AlertError` if closed
- Edit game PUT: `event.is_editing_open()` check, raise `AlertError` if closed

Event player controller (`convergence_games/app/routers/frontend/event_player.py`):
- Preference endpoints: `event.is_preferences_open()` check
- Planner endpoint: `event.is_planner_open()` check

Party controller (`convergence_games/app/routers/frontend/party.py`):
- `check_in()`: enforce `time_slot.checkin_open_time` (currently unenforced)

### Admin bypass

Use existing `user_has_permission()` — check if user has Manager+ role on event. If yes, skip time span checks. Keeps admin access unrestricted.

### Template changes

- Submission/edit forms: show "closed" or "opens at X" messages
- Preferences page: show "opens at X" when gated
- Planner page: show "opens at X" when gated
- Event manager page: add datetime picker fields for each window

## Implementation Plan

### Phase 1: Model + migration

- [x] **Add datetime fields to Event** (`convergence_games/db/models.py`)
  - 5 nullable `DateTimeUTC` columns: `submissions_open_at`, `submissions_close_at`, `editing_close_at`, `preferences_open_at`, `planner_open_at`
- [x] **Add helper methods to Event** (`convergence_games/db/models.py`)
  - `is_submissions_open(now=None) -> bool`
  - `is_editing_open(now=None) -> bool`
  - `is_preferences_open(now=None) -> bool`
  - `is_planner_open(now=None) -> bool`
- [x] **Generate migration**
  - `litestar --app convergence_games.app:app database make-migrations -m "add event time span fields"`

#### Phase 1 verification

- [ ] `basedpyright` — no new errors
- [ ] `ruff check` — no new errors
- [ ] Migration applies cleanly: `litestar --app convergence_games.app:app database upgrade`

### Phase 2: Route enforcement

- [x] **Gate new game submissions** (`convergence_games/app/routers/frontend/submit_game.py`)
  - POST handler: check `event.is_submissions_open()`, raise `AlertError` if closed
  - GET handler: pass `is_submissions_open` to template context
- [x] **Gate game editing** (`convergence_games/app/routers/frontend/submit_game.py`)
  - PUT handler: check `event.is_editing_open()`, raise `AlertError` if closed
  - GET handler: pass `is_editing_open` to template context
- [x] **Gate preferences** (`convergence_games/app/routers/frontend/event_player.py`)
  - Preference endpoints: check `event.is_preferences_open()`, raise `AlertError` if closed
  - Pass `is_preferences_open` to template context
- [x] **Gate planner** (`convergence_games/app/routers/frontend/event_player.py`)
  - Planner endpoint: check `event.is_planner_open()`, raise `AlertError` if closed
  - Pass `is_planner_open` to template context
- [x] **Enforce checkin_open_time** (`convergence_games/app/routers/frontend/party.py`)
  - `check_in()`: reject if `time_slot.checkin_open_time` is set and `now < checkin_open_time`
- [x] **Admin bypass** in all above checks
  - Skip gate if user has Manager+ permission on event

#### Phase 2 verification

- [ ] `basedpyright` — no new errors
- [ ] `ruff check` — no new errors
- [ ] Manual: submit game blocked before `submissions_open_at`
- [ ] Manual: submit game blocked after `submissions_close_at`
- [ ] Manual: edit game blocked after `editing_close_at`
- [ ] Manual: preferences page gated before `preferences_open_at`
- [ ] Manual: planner page gated before `planner_open_at`
- [ ] Manual: admin can bypass all gates

### Phase 3: Event manager UI

- [x] **Add datetime picker fields** to event manager form
  - Fields for each of the 5 datetime windows
  - Clear labeling of what each controls
- [x] **Display current phase status** in event manager dashboard
  - Show which features are currently open/closed based on current time

#### Phase 3 verification

- [ ] Manual: set dates in event manager, verify enforcement changes
- [ ] Manual: clear dates, verify backward-compatible behavior

### Phase 4: Player-facing UI

- [ ] **Submission form** — show "submissions closed" or "opens at X" banner
- [ ] **Edit form** — show "editing closed" banner, disable form
- [ ] **Preferences page** — show "opens at X" message when gated
- [ ] **Planner page** — show "opens at X" message when gated
- [ ] **Navigation** — consider hiding/dimming nav links for gated features

#### Phase 4 verification

- [ ] Manual: verify all gated states show appropriate messages
- [ ] Manual: verify messages include localized datetimes (event timezone)

### Phase 5: Cleanup

- [x] **Remove `FLAG_PREFERENCES` and `FLAG_PLANNER`** from `convergence_games/settings.py`
- [x] **Remove any references** to these flags in templates or code (grep to confirm)

#### Phase 5 verification

- [ ] `basedpyright` — no new errors
- [ ] `ruff check` — no new errors
- [ ] `pytest` — all tests pass
- [ ] Dev server starts without errors

## Acceptance Criteria

- [ ] Type checking passes (`basedpyright`)
- [ ] Linting passes (`ruff check`)
- [ ] All tests pass (`pytest`)
- [ ] Dev server starts without errors
- [ ] Submissions gated by `submissions_open_at` / `submissions_close_at`
- [ ] Editing gated by `submissions_open_at` (open) and `editing_close_at` (close)
- [ ] Preferences gated by `preferences_open_at`
- [ ] Planner gated by `planner_open_at`
- [ ] NULL fields = backward-compatible behavior
- [ ] Admin users bypass all gates
- [ ] Check-in enforces `checkin_open_time`
- [ ] Dead feature flags removed
- [ ] Event manager UI has datetime pickers for all windows

## Risks and Mitigations

1. **Mid-edit save rejection**: If `editing_close_at` passes while GM is editing, save fails. Mitigation: show countdown warning in UI as deadline approaches. Hard rejection at route level is correct — no grace period.
2. **Timezone confusion**: Admin sets dates in event timezone, stored as UTC. Mitigation: display fields in event timezone with clear labels. Helper methods work in UTC internally.
3. **Existing events break**: Adding non-nullable columns would break existing rows. Mitigation: all columns nullable, NULL = backward-compatible defaults.
