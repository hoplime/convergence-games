# Multi-Event Support

## Context

The app has an `Event` model but the frontend hardcodes event ID 1 in several places. For 2026, we need:
- 2025 event archived with its games still viewable
- 2026 event open for submissions
- Same user accounts across events
- A default event concept resolvable from config (no DB lookup per request)
- Event sqid in URLs where needed to disambiguate

Home page content will be replaced with 2026 content manually when ready -- not made dynamic in this change. Event status/phase enum deferred to a later task.

## Current hardcoded locations

| Location                          | What's hardcoded                                          |
| --------------------------------- | --------------------------------------------------------- |
| `event_player.py:87`              | `event_with()` defaults to `event_id = 1`                 |
| `event_manager.py:117`            | Duplicate `event_with()` defaults to `event_id = 1`       |
| `submit_game.py:347,435`          | `event_id = 1` with TODO comments                         |
| `NavBar.html.jinja:41,53`         | `hx-get="/games"`, `hx-get="/planner"` (no event context) |
| `event_games.html.jinja:8`        | Filter form `hx-get="/games"` (no event context)          |
| `home.html.jinja:342,344`         | `href="/games"` links                                     |
| `faq.html.jinja:450`              | `href="/games"` link                                      |
| `my_submissions.html.jinja:28,36` | `hx-get="/submit-game"`, `href="/submit-game"`            |
| `my_submissions.py`               | No event filter on games query                            |

---

## Implementation checklist

### Phase 1: Settings and shared infrastructure

- [ ] **Add `DEFAULT_EVENT_ID` to Settings** (`convergence_games/settings.py`)
  - Add `DEFAULT_EVENT_ID: int = 1`
  - Add `DEFAULT_EVENT_SQID` as `@cached_property` using deferred `swim("Event", self.DEFAULT_EVENT_ID)` import to avoid circular dep with `ocean.py`

- [ ] **Consolidate `event_with()` dependency** (`convergence_games/app/app_config/dependencies.py`)
  - Move `event_with()` from `event_player.py` and `event_manager.py` into shared dependencies
  - Replace hardcoded `1` with `SETTINGS.DEFAULT_EVENT_ID`
  - Update imports in `event_player.py` and `event_manager.py`

### Phase 2: Route restructuring

- [ ] **Create redirect handlers** (`convergence_games/app/routers/frontend/redirects.py` -- new file)
  - `GET /games` -> 302 to `/event/{DEFAULT_EVENT_SQID}/games`
  - `GET /planner` -> 302 to `/event/{DEFAULT_EVENT_SQID}/planner`
  - `GET /submit-game` -> 302 to `/event/{DEFAULT_EVENT_SQID}/submit-game`

- [ ] **Register redirects controller** (`convergence_games/app/routers/frontend/__init__.py`)
  - Import and add `RedirectsController` to the router's `route_handlers`

- [ ] **Remove shortcut paths from event_player routes** (`convergence_games/app/routers/frontend/event_player.py`)
  - Line 353: Remove `/games` from route list -> `["/event/{event_sqid:str}", "/event/{event_sqid:str}/games"]`
  - Line 410: Remove `/planner` from route list -> `["/event/{event_sqid:str}/planner", "/event/{event_sqid:str}/planner/{time_slot_sqid:str}"]`

- [ ] **Make submit-game event-scoped** (`convergence_games/app/routers/frontend/submit_game.py`)
  - `get_submit_game`: path `/submit-game` -> `/event/{event_sqid:str}/submit-game`, use shared `event_with()`
  - `post_game`: path `/game` -> `/event/{event_sqid:str}/game`, use shared `event_with()` instead of `event_id = 1`
  - Remove hardcoded `event_id = 1` at lines 347 and 435
  - `put_game` and `put_game_submission_status` unchanged (get event from existing game)

### Phase 3: Template updates

- [ ] **NavBar** (`convergence_games/app/templates/components/NavBar.html.jinja`)
  - Line 41: `hx-get="/games"` -> `hx-get="/event/{{ SETTINGS.DEFAULT_EVENT_SQID }}/games"`
  - Line 53: `hx-get="/planner"` -> `hx-get="/event/{{ SETTINGS.DEFAULT_EVENT_SQID }}/planner"`

- [ ] **Event games page** (`convergence_games/app/templates/pages/event_games.html.jinja`)
  - Line 3: Title `Convergence 2025` -> `{{ event.name }}`
  - Line 8: Filter form `hx-get="/games"` -> `hx-get="/event/{{ swim(event) }}/games"` (uses current event, not default)

- [ ] **My submissions page** (`convergence_games/app/templates/pages/my_submissions.html.jinja`)
  - Line 28: `hx-get="/submit-game"` -> `hx-get="/event/{{ SETTINGS.DEFAULT_EVENT_SQID }}/submit-game"`
  - Line 36: `href="/submit-game"` -> `href="/event/{{ SETTINGS.DEFAULT_EVENT_SQID }}/submit-game"`

- [ ] **Home page** (`convergence_games/app/templates/pages/home.html.jinja`)
  - Line 342, 344: `href="/games"` -> `href="/event/{{ SETTINGS.DEFAULT_EVENT_SQID }}/games"`

- [ ] **FAQ page** (`convergence_games/app/templates/pages/faq.html.jinja`)
  - Line 450: `href="/games"` -> `href="/event/{{ SETTINGS.DEFAULT_EVENT_SQID }}/games"`

### Phase 4: My submissions improvements

- [ ] **Update my_submissions query** (`convergence_games/app/routers/frontend/my_submissions.py`)
  - Add `selectinload(Game.event)` to the query
  - Order by event `start_date` descending, then game name
  - Group games by event in template context

- [ ] **Update my_submissions template** (`convergence_games/app/templates/pages/my_submissions.html.jinja`)
  - Show games grouped by event with event name as section header
  - Most recent event first

### Phase 5: Verification

- [ ] `uv run basedpyright` passes
- [ ] `uv run ruff check` passes
- [ ] Dev server starts without errors
- [ ] `/games` redirects to `/event/{sqid}/games`
- [ ] `/planner` redirects to `/event/{sqid}/planner`
- [ ] `/submit-game` redirects to `/event/{sqid}/submit-game`
- [ ] Filter form on games page stays within event context (no redirect loop)
- [ ] NavBar buttons navigate to event-scoped URLs
- [ ] My Submissions shows games grouped by event
- [ ] Game submission creates game under correct event

---

## Key risks and mitigations

1. **HTMX partials and redirects**: If any `hx-get` still points to a shortcut URL, the 302 will break partial rendering. All template `hx-get`/`hx-post` MUST use event-scoped URLs directly. The redirects are only for browser navigation / old bookmarks.

2. **Circular import**: `Settings.DEFAULT_EVENT_SQID` needs `swim()` from `ocean.py` which imports `SETTINGS`. Deferred import inside `@cached_property` avoids this.

3. **submit_game POST**: The `post_game` handler creates a new game and needs `event_id`. Currently hardcoded. Must verify how the handler receives event context and ensure the form submission URL includes the event sqid.

## Files to modify

| File                                                       | Change                                             |
| ---------------------------------------------------------- | -------------------------------------------------- |
| `convergence_games/settings.py`                            | Add `DEFAULT_EVENT_ID` and `DEFAULT_EVENT_SQID`    |
| `convergence_games/app/app_config/dependencies.py`         | Add shared `event_with()`                          |
| `convergence_games/app/routers/frontend/redirects.py`      | **Create** -- redirect handlers                    |
| `convergence_games/app/routers/frontend/__init__.py`       | Register redirects controller                      |
| `convergence_games/app/routers/frontend/event_player.py`   | Remove local `event_with()`, remove shortcut paths |
| `convergence_games/app/routers/frontend/event_manager.py`  | Remove local `event_with()`, import shared         |
| `convergence_games/app/routers/frontend/submit_game.py`    | Make event-scoped, use shared `event_with()`       |
| `convergence_games/app/routers/frontend/my_submissions.py` | Add event loading, order/group by event            |
| `NavBar.html.jinja`                                        | Event-scoped nav links                             |
| `event_games.html.jinja`                                   | Event-scoped filter form, dynamic title            |
| `my_submissions.html.jinja`                                | Event-scoped submit link, group by event           |
| `home.html.jinja`                                          | Event-scoped games link                            |
| `faq.html.jinja`                                           | Event-scoped games link                            |
