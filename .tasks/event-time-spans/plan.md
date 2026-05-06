---
title: Event time span gating
created: 2026-05-06
status: in-progress
---

# Event Time Span Gating

## Context

Event model had no phase/state controls. Game submission, editing, preferences, and planner were all ungated. Only phase control was `TimeSlotStatus` per-timeslot (gates party formation, freezes preferences at allocation). Feature flags `FLAG_PREFERENCES` / `FLAG_PLANNER` existed in settings but were unused.

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

5 nullable `DateTimeUTC` columns on Event (`convergence_games/db/models.py`):
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
- New game GET/POST: `event.is_submissions_open()` check, raise `AlertError` if closed
- Edit game GET/PUT: `event.is_editing_open()` check, raise `AlertError` if closed

Game controller (`convergence_games/app/routers/frontend/game.py`):
- Preference PUT: `event.is_preferences_open()` check, raise `AlertError` if closed

Event player controller (`convergence_games/app/routers/frontend/event_player.py`):
- Planner GET: `event.is_planner_open()` check → renders dedicated closed page instead of AlertError

Party controller (`convergence_games/app/routers/frontend/party.py`):
- `check_in()`: enforce `time_slot.checkin_open_time` (was unenforced)

### Admin bypass

Use existing `user_has_permission()` — check if user has Manager+ role on event via `manage_submissions` permission. Keeps admin access unrestricted.

### Template changes

- Preference dice hidden on GameCard/game page when `is_preferences_open()` false
- Planner time slot dots hidden on GameCard when `is_planner_open()` false
- Planner nav link always visible (route guard enforces; NavBar lacks event context)
- Game page: edit button disabled when editing closed
- My submissions: edit buttons disabled per-event, submit buttons per-event as list rows
- Planner closed: dedicated page with open date, links to games/preferences
- Event manager: settings page with datetime pickers grouped by audience (GM/Player)
- Settings page displays/accepts times in event timezone, stores as UTC

## Implementation Plan

### Phase 1: Model + migration

- [x] **Add datetime fields to Event** (`convergence_games/db/models.py`)
- [x] **Add helper methods to Event** (`convergence_games/db/models.py`)
- [x] **Generate and apply migration**

### Phase 2: Route enforcement

- [x] **Gate new game submissions** (`submit_game.py`) — GET and POST
- [x] **Gate game editing** (`submit_game.py`) — GET and PUT
- [x] **Gate preferences** (`game.py`) — PUT preference endpoint
- [x] **Gate planner** (`event_player.py`) — GET renders closed page
- [x] **Enforce checkin_open_time** (`party.py`)
- [x] **Admin bypass** via `user_has_permission` in all checks

### Phase 3: Event manager UI

- [x] **Settings page** (`event_manage_settings.html.jinja`) — datetime pickers grouped into GM/Player fieldsets
- [x] **Status badges** inline with controlling inputs
- [x] **Timezone handling** — display in event timezone, convert to UTC on save
- [x] **HX-Redirect** instead of 302 Redirect to avoid HTMX loop
- [x] **Admin nav link** in AdminSectionCard

### Phase 4: Player-facing UI

- [x] **Planner closed page** (`event_planner_closed.html.jinja`) — explains status, shows open date, links to games/preferences
- [x] **GameCard** — preference dice and planner dots gated by event methods
- [x] **Game page** — edit button disabled when editing closed, scheduled sessions gated by planner
- [x] **My submissions** — edit buttons disabled per-event, submit row per-event, empty state with default event
- [x] **NavBar** — planner link always visible for logged-in users (route guard enforces)
- [ ] **Submission/edit form pages** — show banner when approaching deadline (nice-to-have)

### Phase 5: Cleanup

- [x] **Remove `FLAG_PREFERENCES` and `FLAG_PLANNER`** from settings and all templates
- [x] **Remove dead `.env` entries** (`FLAG_PREFERENCES=true`, `FLAG_PLANNER=true`)

### Remaining

- [ ] Manual browser testing of all gated states
- [ ] Verify admin bypass works for all gates
- [ ] Verify NULL fields = backward-compatible behavior

## Acceptance Criteria

- [x] Type checking passes (`basedpyright`) — no new errors
- [x] Linting passes (`ruff check`) — no new errors
- [x] All tests pass (`pytest`)
- [x] Submissions gated by `submissions_open_at` / `submissions_close_at`
- [x] Editing gated by `submissions_open_at` (open) and `editing_close_at` (close)
- [x] Preferences gated by `preferences_open_at`
- [x] Planner gated by `planner_open_at`
- [x] NULL fields = backward-compatible behavior (code-level)
- [x] Admin users bypass all gates (code-level)
- [x] Check-in enforces `checkin_open_time`
- [x] Dead feature flags removed
- [x] Event manager UI has datetime pickers for all windows
- [ ] Manual verification of all above in browser

## Risks and Mitigations

1. **Mid-edit save rejection**: If `editing_close_at` passes while GM is editing, save fails. Mitigation: hard rejection at route level is correct — no grace period. Nice-to-have: countdown warning in UI.
2. **Timezone confusion**: Admin sets dates in event timezone, stored as UTC. Mitigation: settings page displays in event timezone with clear label. Helper methods work in UTC internally.
3. **Existing events break**: Adding non-nullable columns would break existing rows. Mitigation: all columns nullable, NULL = backward-compatible defaults.
