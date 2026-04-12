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

- [x] **Add `DEFAULT_EVENT_ID` to Settings** (`convergence_games/settings.py`)
  - Add `DEFAULT_EVENT_ID: int = 1`
  - Add `DEFAULT_EVENT_SQID` as `@cached_property` using deferred `swim("Event", self.DEFAULT_EVENT_ID)` import to avoid circular dep with `ocean.py`

- [x] **Consolidate `event_with()` dependency** (`convergence_games/app/routers/frontend/common.py` -- new file)
  - Move `event_with()` from `event_player.py` and `event_manager.py` into shared `common.py`
  - Replace hardcoded `1` with `SETTINGS.DEFAULT_EVENT_ID`
  - Update imports in `event_player.py` and `event_manager.py`

### Phase 2: Route restructuring

- [x] **Create redirect handlers** (`convergence_games/app/routers/frontend/redirects.py` -- new file)
  - `GET /games` -> 302 to `/event/{DEFAULT_EVENT_SQID}/games`
  - `GET /planner` -> 302 to `/event/{DEFAULT_EVENT_SQID}/planner`
  - `GET /submit-game` -> 302 to `/event/{DEFAULT_EVENT_SQID}/submit-game`

- [x] **Register redirects controller** (`convergence_games/app/routers/frontend/__init__.py`)
  - Import and add `RedirectsController` to the router's `route_handlers`

- [x] **Remove shortcut paths from event_player routes** (`convergence_games/app/routers/frontend/event_player.py`)
  - Remove `/games` from route list -> `["/event/{event_sqid:str}", "/event/{event_sqid:str}/games"]`
  - Remove `/planner` from route list -> `["/event/{event_sqid:str}/planner", "/event/{event_sqid:str}/planner/{time_slot_sqid:str}"]`

- [x] **Make submit-game event-scoped** (`convergence_games/app/routers/frontend/submit_game.py`)
  - `get_submit_game`: path `/event/{event_sqid:str}/submit-game`, uses shared `event_with()`
  - `post_game`: path `/event/{event_sqid:str}/game`, uses shared `event_with()`
  - Template form `hx-post` updated to `/event/{{ swim(event) }}/game`
  - `put_game` and `put_game_submission_status` unchanged (get event from existing game)

### Phase 3: Template updates

- [x] **NavBar** (`convergence_games/app/templates/components/NavBar.html.jinja`)
  - `hx-get="/games"` -> `hx-get="/event/{{ SETTINGS.DEFAULT_EVENT_SQID }}/games"`
  - `hx-get="/planner"` -> `hx-get="/event/{{ SETTINGS.DEFAULT_EVENT_SQID }}/planner"`

- [x] **Event games page** (`convergence_games/app/templates/pages/event_games.html.jinja`)
  - Title: removed hardcoded `- Convergence 2025` suffix
  - Filter form `hx-get="/games"` -> `hx-get="/event/{{ swim(event) }}/games"` (uses current event, not default)

- [x] **My submissions page** (`convergence_games/app/templates/pages/my_submissions.html.jinja`)
  - `hx-get="/submit-game"` -> `hx-get="/event/{{ SETTINGS.DEFAULT_EVENT_SQID }}/submit-game"`
  - `href="/submit-game"` -> `href="/event/{{ SETTINGS.DEFAULT_EVENT_SQID }}/submit-game"`

- [x] **Home page** (`convergence_games/app/templates/pages/home.html.jinja`)
  - `href="/games"` -> `href="/event/{{ SETTINGS.DEFAULT_EVENT_SQID }}/games"`

- [x] **FAQ page** (`convergence_games/app/templates/pages/faq.html.jinja`)
  - `href="/games"` -> `href="/event/{{ SETTINGS.DEFAULT_EVENT_SQID }}/games"`

**Follow-up task**: Extract hardcoded "Convergence 2025" from `<title>` tags across all page templates into a setting/constant.

### Phase 4: My submissions improvements

- [x] **Update my_submissions query** (`convergence_games/app/routers/frontend/my_submissions.py`)
  - Add `selectinload(Game.event)` to the query
  - Join on Event, order by `Event.start_date` descending, then `Game.name`
  - Group games by event using `itertools.groupby` (safe because query is pre-sorted)

- [x] **Update my_submissions template** (`convergence_games/app/templates/pages/my_submissions.html.jinja`)
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
| `convergence_games/app/routers/frontend/common.py`         | **Create** -- shared `event_with()`                |
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
