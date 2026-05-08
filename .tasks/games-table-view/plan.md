---
title: Alternate table view for the event games page
created: 2026-05-08
status: draft
---

# Alternate table view for the event games page

## Context

The event games page (`/event/{event_sqid}/games`) currently renders games as a responsive grid of `GameCard` components. Cards are friendly but inefficient on desktop — each card occupies a lot of vertical space, and there is no way to compare games across attributes at a glance, or to sort by an attribute (name, system, GM, tone).

We want an alternate **table view** that renders one row per game with sortable column headings, while keeping the card view as the default. The user picks the view via a toggle in the page header; the choice is reflected in the URL so it is shareable and works with the back button.

For now, filtering continues to use the existing side drawer (shared between both views). Per-column header filter popovers may come in a follow-up task.

## Requirements

- Users can switch between **cards** and **table** views via a clear toggle on the games page.
- Selected view is reflected in the URL as `?view=cards` (default) or `?view=table`, so it is shareable and survives back/forward navigation.
- Table view is shown only on viewports `md` and above; on smaller viewports the page renders cards regardless of `?view`.
- The table includes columns: **Name**, **System**, **Gamemaster**, **Tone**, **Genres**, **Preference** (Preference column hidden when the user is logged out or preferences are not open).
- Columns **Name**, **System**, **Gamemaster**, **Tone** are sortable via clickable column headers; clicking again toggles ascending/descending.
- Sort state is reflected in the URL as `?sort=<col>&desc=<bool>` and applied server-side in the SQL query.
- Existing filter drawer continues to work in both views; switching view preserves active filters and sort state in the URL.
- Existing HTMX partial-swap behaviour for filter changes continues to work in both views (no full page reload when filters change).
- Game name in the table links to the game detail page (same as the card view).
- Preference column renders the existing `DiceRating` widget with the same behaviour as `GameCard` (logged-in, non-GM, age-appropriate).

## Technical Design

### URL surface

The existing handler `EventPlayerController.get_event_games` (`convergence_games/app/routers/frontend/event_player.py:348`) gains two additional query parameters in `EventGamesQuery`:

- `view: Literal["cards", "table"] = "cards"`
- `sort: Literal["name", "system", "gamemaster", "tone"] | None = None`
- `desc: bool = False`

`event_games_query_from_params_dep` is extended to accept and pass through `view`, `sort`, `desc`. The defaults keep current behaviour byte-identical when no new params are present.

### Server-side sorting

`get_event_approved_games_dep` (`convergence_games/app/routers/frontend/event_player.py:82`) currently does `.order_by(Game.name)`. Replace with a small mapping:

```python
sort_columns = {
    "name": Game.name,
    "system": System.name,
    "gamemaster": User.full_name,
    "tone": Game.tone,
}
```

When `query_params.sort` is `system`, add `.join(System, Game.system_id == System.id)`; when `gamemaster`, add `.join(User, Game.gamemaster_id == User.id)`. Apply `.order_by(col.desc() if query_params.desc else col.asc())`. Always add `Game.name` as a secondary tie-breaker (so order is deterministic when sort-key values match). Default (`sort is None`) remains `.order_by(Game.name)`.

### Template structure

Refactor `convergence_games/app/templates/pages/event_games.html.jinja` so the existing `{% block game_list %}` swap target wraps a single container whose internal layout depends on `view`:

```
<div id="game_list">
  {% if view == "table" %}
    <div class="hidden md:block">{# table #}</div>
    <div class="grid ... md:hidden">{# cards #}</div>
  {% else %}
    <div class="grid ...">{# cards #}</div>
  {% endif %}
</div>
```

This keeps the existing `hx-target="#game_list"` and the `block_name=request.htmx.target` flow intact: filter and sort changes both swap the same block, so HTMX does not need to know about the view distinction.

### View toggle

Add a small toggle next to the existing filter drawer button. Two pill-style links rendered as `<a>` with `hx-get` (so they participate in the HTMX swap pipeline) and `hx-push-url="true"`, pointing at `/event/{sqid}/games?view=cards|table` while preserving current query string values via `hx-include="#filter_form"`. Active variant uses `btn-primary`; inactive uses `btn-outline`.

The toggle is always visible (cards toggle remains useful on mobile to revert if a table-view link was shared). When the table is forced to cards by viewport (`<md`), the toggle still shows the user's stored preference value — there is no JS-driven mismatch handling because the cards/table swap is purely CSS-driven via Tailwind responsive classes.

### Sort header component

`TableSortHeader.html.jinja` currently hardcodes `hx-get="manage-submissions?sort=…"` and `hx-target="#content"`. Generalise it to accept `url` and `target` props, with the existing call site in `event_manage_submissions.html.jinja` updated to pass them explicitly. Keep the active/desc visual logic as-is.

```jinja
{#def
    sort: str,
    url: str,
    target: str = "#content",
    active: bool = False,
    desc: bool = False,
#}
```

Call site for the games page passes `url="/event/{{ swim(event) }}/games?view=table"` plus the inherited filter values (using `hx-include="#filter_form"`), and `target="#game_list"`.

### Game row component

Add `convergence_games/app/templates/components/GameRow.html.jinja` modelled on `GameCard.html.jinja` but rendering a `<tr>` with `<td>` per column. Props:

```
game: Game,
preference: int | None = None,
user_game_played: UserGamePlayed | None = None,
display_d20: bool = False,
show_preference_column: bool = False,
```

Columns:
1. **Name** — `<a href="/game/{{ swim(game) }}">{{ game.name }}</a>`, with `<div class="text-sm italic text-base-content/70">{{ game.tagline }}</div>` underneath.
2. **System** — `game.system.name`.
3. **Gamemaster** — `game.gamemaster.full_name`.
4. **Tone** — `<div class="badge badge-sm">{{ game.tone }}</div>`.
5. **Genres** — wrapped flex row of `badge badge-sm badge-outline` (same markup as `GameCard`).
6. **Preference** (only if `show_preference_column`) — same gating logic as `GameCard` (`game.event.is_preferences_open()`, `request.user.id == game.gamemaster_id`, R18 check) wrapping `DiceRating`. Reuse the existing component; do not duplicate its HTML.

The "no games found" empty state is rendered as a single `<tr><td colspan="…">…</td></tr>` when in table view, to mirror the existing card-view empty state.

### Files changed

| File | Change |
| --- | --- |
| `convergence_games/app/routers/frontend/event_player.py` | Extend `EventGamesQuery` and `event_games_query_from_params_dep` with `view`, `sort`, `desc`. Apply sort + joins in `get_event_approved_games_dep`. Pass `view` into the template context. |
| `convergence_games/app/templates/pages/event_games.html.jinja` | Add view toggle next to the filter button. Branch the `game_list` block on `view`. Render the table when `view == "table"` (md+ only). Pass new `url`/`target` props to `TableSortHeader`. |
| `convergence_games/app/templates/components/TableSortHeader.html.jinja` | Add `url` and `target` props; replace hardcoded URL/target. |
| `convergence_games/app/templates/pages/event_manage_submissions.html.jinja` | Update existing `TableSortHeader` calls to pass `url="manage-submissions"` (preserving current behaviour). |
| `convergence_games/app/templates/components/GameRow.html.jinja` | New component rendering a single `<tr>` for the table view. |

No DB schema changes, no new migrations.

## Implementation Plan

### Phase 1: Backend — query params and sort

- [ ] **Extend `EventGamesQuery`** (`convergence_games/app/routers/frontend/event_player.py`)
  - Add `view: Literal["cards", "table"] = "cards"`.
  - Add `sort: Literal["name", "system", "gamemaster", "tone"] | None = None`.
  - Add `desc: bool = False`.
- [ ] **Extend `event_games_query_from_params_dep`** (same file)
  - Accept matching parameters and pass them into `EventGamesQuery.model_validate`.
- [ ] **Apply sort in `get_event_approved_games_dep`** (same file)
  - Build a `sort_columns` mapping.
  - When sorting by `system` or `gamemaster`, add the appropriate join.
  - Apply `.asc()`/`.desc()` from `query_params.desc`.
  - Always append `Game.name.asc()` as a tie-breaker.
- [ ] **Pass `view` into template context** in `get_event_games` so the template can branch.

#### Phase 1 verification

- [ ] `basedpyright` — no new errors.
- [ ] `ruff check` — no new errors.
- [ ] Manually hit `/event/{sqid}/games?sort=system&desc=true` and confirm the underlying SQL orders by `system.name DESC, games.name ASC` (e.g. with SQLAlchemy echo or a quick `pytest` against the dependency).

### Phase 2: Frontend — generalise `TableSortHeader`

- [ ] **Add `url` and `target` props to `TableSortHeader.html.jinja`** (`convergence_games/app/templates/components/TableSortHeader.html.jinja`)
  - Replace hardcoded `manage-submissions` and `#content` with `{{ url }}` and `{{ target }}`.
- [ ] **Update existing call site** (`convergence_games/app/templates/pages/event_manage_submissions.html.jinja`)
  - Pass `url="manage-submissions"` (and rely on default `target="#content"`).

#### Phase 2 verification

- [ ] Load `/event/{sqid}/manage-submissions`, click each sortable header — sorting still works exactly as before.
- [ ] `npx tsc --noEmit` — no errors (no TS changes in this phase, sanity check only).

### Phase 3: Frontend — `GameRow` component and table layout

- [ ] **Create `GameRow.html.jinja`** (`convergence_games/app/templates/components/GameRow.html.jinja`)
  - Implement the columns described in Technical Design.
  - Reuse `DiceRating` and gating logic from `GameCard`.
- [ ] **Update `event_games.html.jinja`** (`convergence_games/app/templates/pages/event_games.html.jinja`)
  - Inside the `game_list` block, branch on `view`.
  - For table view, render `<table class="table table-sm bg-base-200 hidden md:table">` with a `<thead>` of `TableSortHeader` cells (Name/System/GM/Tone) plus plain `<th>` for Genres and Preference.
  - Render a `<tr>` per game using `GameRow`.
  - Below the table, on `<md`, render the existing card grid as a fallback (`md:hidden`).
  - Handle empty state with a single `<tr><td colspan="…">…</td></tr>`.

#### Phase 3 verification

- [ ] Load `/event/{sqid}/games?view=table` on a desktop viewport — table renders with all expected columns.
- [ ] Resize to mobile (`<md`) — cards render instead of the table.
- [ ] `ruff check` and `basedpyright` — no new errors.

### Phase 4: View toggle

- [ ] **Add toggle UI to `event_games.html.jinja`**
  - Render two pill buttons (Cards / Table) next to the filter button.
  - Each is an `<a>` with `hx-get`, `hx-target="#game_list"`, `hx-push-url="true"`, and `hx-include="#filter_form"` so existing filters carry through.
  - Apply `btn-primary` to the active view and `btn-outline` to the other.

#### Phase 4 verification

- [ ] Toggle from cards → table — URL updates to `?view=table`, page swaps to table without a full reload.
- [ ] Apply a filter, then toggle view — filter remains active and is reflected in the URL.
- [ ] Use the browser back button — previous view is restored.

### Phase 5: Wire up sort on the games table

- [ ] **Pass URL + sort/desc into `TableSortHeader` call sites** in `event_games.html.jinja`
  - Each header receives `url="/event/{{ swim(event) }}/games"`, `target="#game_list"`, plus `:active` and `:desc` based on `query_params.sort` / `query_params.desc`.
  - Use `hx-include="#filter_form"` on the headers so active filters and `view=table` carry through. (May require a small additional attribute on `TableSortHeader` — confirm during implementation; alternatively encode `view=table` directly in `url`.)

#### Phase 5 verification

- [ ] Click each sortable header — order updates and URL gains `?sort=…&desc=…`.
- [ ] Click the same header again — direction toggles.
- [ ] Apply a filter, then sort — both apply correctly and persist in the URL.
- [ ] Switch to card view — sort param is preserved in URL but has no visible effect (acceptable).

## Acceptance Criteria

- [ ] `basedpyright` passes.
- [ ] `ruff check` passes.
- [ ] Existing tests still pass: `pytest`.
- [ ] Dev server starts without errors.
- [ ] `/event/{sqid}/games` (no params) renders cards exactly as it does today.
- [ ] `/event/{sqid}/games?view=table` renders the table view on desktop and falls back to cards below `md`.
- [ ] Sort headers (Name, System, GM, Tone) update the URL and re-order rows server-side; clicking the active header toggles direction.
- [ ] Filter drawer continues to work in both views and combines correctly with sort.
- [ ] `event_manage_submissions` page still sorts correctly after `TableSortHeader` is generalised.

## Risks and Mitigations

1. **`hx-include` semantics with sort headers**: `TableSortHeader`'s current `hx-get` is a literal URL with the sort params baked in. Combining that with `hx-include="#filter_form"` may double-include or conflict. Mitigation: prefer encoding `sort`, `desc`, and `view` directly into the `url` prop, and use `hx-include` only for the filter form so there is one source of truth per parameter group. Verify during Phase 5.
2. **Preference column gating duplication**: The `GameCard` has non-trivial logic around when to show the rating (R18, GM-of-this-game, party rules). Mitigation: keep `GameRow` strictly mirroring `GameCard`'s checks and pull the shared snippet into a JinjaX helper if duplication starts to drift. For this task, simple duplication is acceptable.
3. **HTMX block swap loses `id="game_list"`**: If the swap returns markup that doesn't have the `id`, subsequent swaps break. Mitigation: keep the `<div id="game_list">` wrapper outside the `view` branch — the branch only chooses what's inside it.
4. **Sort by relationship attribute requires a join**: If a join is missing, `order_by(System.name)` fails. Mitigation: explicit conditional `.join(System, ...)` / `.join(User, ...)` in `get_event_approved_games_dep`. Confirm via Phase 1 verification.

## Notes

- Out of scope: per-column header filter popovers; saving the user's view preference across sessions; sorting by genre or content warning counts; mobile stacked-row layout. Any of these can be follow-up tasks.
- The chosen column set (Name, System, GM, Tone, Genres, Preference) is intentionally compact; adding Classification, Crunch, Bonus, Sessions dots, or Content warnings is a small additional task once the structure lands.
