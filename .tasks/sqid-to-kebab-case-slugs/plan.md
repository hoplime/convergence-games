---
title: Kebab-case slug URLs for public-facing routes
created: 2026-05-07
status: draft
---

# Kebab-case slug URLs for public-facing routes

## Context

Public URLs currently use opaque sqid strings (e.g. `/event/Xy7aB/games`, `/game/PqR9w`). They are stable and obfuscate IDs but are unreadable, unmemorable, and ugly when shared on social media or printed in event materials. The desired form is a human-readable slug derived from the entity name:

- `/event/convergence-2026/games` — event games listing
- `/event/convergence-2026/game/dragons-of-doom` — individual game info page
- `/event/convergence-2026/planner` — session planner (event scope)

Internal mutation endpoints (HTMX `PUT`/`POST`, admin `manage-*` controllers, allocation, party lifecycle) should continue using sqids — those URLs are not user-shared, the sqid is convenient as a `BeforeValidator`-decoded `int`, and the churn would be enormous for no user-visible benefit.

Old copied URLs containing sqids must continue to resolve. They should `301` redirect to the canonical slug URL so search engines and users converge on one form.

## Requirements

- `Event`, `Game`, and `User` rows expose a stable, human-readable `slug` column.
- Slugs are auto-generated from a source field on insert and never change after creation.
  - `Event.slug` derived from `Event.name`.
  - `Game.slug` derived from `Game.name`.
  - `User.slug` derived from `f"{first_name} {last_name}"` (trimmed if last name empty).
- Slug uniqueness scopes:
  - `Event.slug` and `User.slug`: globally unique (table-wide).
  - `Game.slug`: unique per `event_id` (composite unique constraint).
- On slug collision the Advanced Alchemy default applies: append a 4-char `[a-z0-9]` suffix, e.g. `convergence-2026-x7q3`.
- Public-facing GET routes accept slugs as path parameters:
  - `/event/{event_key}` and `/event/{event_key}/games` (event landing + games list)
  - `/event/{event_key}/game/{game_key}` (game info page — moved from top-level `/game/{sqid}`)
  - `/event/{event_key}/planner` and `/event/{event_key}/planner/{time_slot_sqid}` (TimeSlot keeps sqid)
- Mutation endpoints (PUT/POST/DELETE), HTMX partial endpoints, `/event/{...}/manage-*` admin pages, party lifecycle paths, and OAuth/auth flows continue using sqids unchanged.
- Old sqid URLs for slug-enabled GETs return HTTP 301 to the canonical slug URL — never break a copied link.
- Existing rows in production are backfilled in the same Alembic migration that adds the columns; no separate manual step.
- `request.app.url_for(...)` callers and template helpers updated so links emitted server-side use the slug form.
- `pytest`, `ruff check`, and `basedpyright` all pass.

## Technical Design

### Slug column via Advanced Alchemy `SlugKey` mixin

Advanced Alchemy ships `advanced_alchemy.mixins.SlugKey` (`from advanced_alchemy.mixins import SlugKey`). It declares:

- `slug: Mapped[str]` (declared_attr)
- a unique constraint `uq_{tablename}_slug`
- a unique index `ix_{tablename}_slug_unique`

Mix it into `Event`, `User` directly. For `Game`, mix it in but **override** `__table_args__` so the slug uniqueness becomes composite `(event_id, slug)` instead of global. Pattern:

```python
class Game(Base, SlugKey):
    ...
    @declared_attr.directive
    @classmethod
    def __table_args__(cls):
        return (
            UniqueConstraint("event_id", "slug", name="uq_game_event_slug"),
            Index("ix_game_event_slug_unique", "event_id", "slug", unique=True),
            # plus existing constraints from current Game definition
        )
```

The default `SlugKey.__table_args__` is dropped on Game in favour of the composite. Existing `Game` table args (none beyond audit columns today) are preserved.

### Slug generation

Use Advanced Alchemy's helper: `from advanced_alchemy.utils.text import slugify`. It lowercases, replaces whitespace and underscores with hyphens, strips diacritics, and removes non-`[a-z0-9-]` characters.

Add a single helper in a new module `convergence_games/db/slugs.py`:

```python
async def generate_unique_slug(
    session: AsyncSession,
    model: type[Base],
    source: str,
    *,
    scope: dict[str, Any] | None = None,
) -> str:
    base = slugify(source) or "untitled"
    candidate = base
    while await _slug_exists(session, model, candidate, scope=scope):
        suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
        candidate = f"{base}-{suffix}"
    return candidate
```

`_slug_exists` issues a single `SELECT 1 ... LIMIT 1` filtering by `slug` and any scope keys (e.g. `{"event_id": ...}` for Game).

This replicates `SQLAlchemyAsyncSlugRepository.get_available_slug` but works with a plain session and supports scoping. We do not need to introduce a full Repository class for this.

### Where slugs are populated

Auto-populate at the route/service layer when an entity is created — not via SQLAlchemy `before_insert` (that hook is sync and cannot await a uniqueness check). Touch points:

- `convergence_games/app/routers/frontend/submit_game.py` — when a Game is inserted, call `generate_unique_slug(session, Game, game.name, scope={"event_id": game.event_id})` and assign before flush.
- `convergence_games/db/create_mock_data.py` and `convergence_games/services/mock_event.py` (if it creates events/games) — populate slugs when seeding.
- Any other Event/Game/User insert site (search via `Event(`, `Game(`, `User(` constructor calls). Shortlist found:
  - `convergence_games/app/routers/frontend/oauth.py` — User creation on first OAuth login (use first_name + last_name).
  - `convergence_games/app/routers/frontend/email_auth.py` — User creation on first email signup.
  - `convergence_games/app/routers/frontend/event_manager.py` — anywhere new Events/Games are created administratively (currently none, but verify).
  - Admin event creation flow if/when one exists.

### Path resolution & sqid fallback

A new dependency in `convergence_games/app/routers/frontend/common.py` replaces `event_with`:

```python
def event_with(*options: ExecutableOption) -> Provide:
    async def wrapper(
        request: Request,
        transaction: AsyncSession,
        event_key: str | None = None,
    ) -> Event:
        if event_key is None:
            event_id = SETTINGS.DEFAULT_EVENT_ID
            stmt = select(Event).options(*options).where(Event.id == event_id)
        else:
            stmt = select(Event).options(*options).where(Event.slug == event_key)
        event = (await transaction.execute(stmt)).scalar_one_or_none()
        if event is None and event_key is not None and _looks_like_sqid(event_key):
            event_id = sink(cast(Sqid, event_key))
            stmt = select(Event).options(*options).where(Event.id == event_id)
            event = (await transaction.execute(stmt)).scalar_one_or_none()
            if event is not None:
                raise SlugRedirect(canonical_event_path(request, event))
        if event is None:
            raise HTTPException(status_code=404, detail="Event not found")
        return event
    return Provide(wrapper)
```

`_looks_like_sqid(value)` returns True when the value contains no `-` and is not all `[a-z0-9]+` shape that matches a likely slug (cheap heuristic: any uppercase character, OR length matches `SQIDS_MIN_LENGTH` and no hyphens). Since slugs are forced lowercase and sqids use the default mixed-case alphabet, the presence of any uppercase character is a strong sqid signal; lowercase-only ambiguous values can fall through to a sqid decode attempt wrapped in try/except.

`SlugRedirect` is a new exception in `convergence_games/app/exceptions.py` (or `alerts.py` adjacent). A handler registered in `convergence_games/app/app_config/exception_handlers.py` returns `Redirect(path=..., status_code=301)`.

`canonical_event_path(request, event)` rebuilds the current URL substituting `event.slug` for the matched parameter. Because Litestar exposes `request.path_params`, we can:

```python
new_params = {**request.path_params, "event_key": event.slug}
return request.app.route_reverse(handler_name, **new_params)
```

For Game, parallel handling: a new path `/event/{event_key:str}/game/{game_key:str}` resolves both (event by slug-or-sqid, game by slug-or-sqid scoped to `event.id`). The legacy path `/game/{game_sqid:str}` stays in `GameController` but its GET only — sole behaviour is to decode the sqid, look up the game, then 301-redirect to the canonical slug URL. PUT mutations on `/game/{game_sqid}/preference` and `/game/{game_sqid}/already-played` remain unchanged.

### Default event sqid setting

`convergence_games/settings.py` currently exposes `DEFAULT_EVENT_SQID` (computed from `DEFAULT_EVENT_ID`). Add `DEFAULT_EVENT_KEY` returning the slug — but because settings are loaded before the DB, this needs to be either:

- a settings field overridden via `.env` (string slug, e.g. `DEFAULT_EVENT_KEY=convergence-2026`), or
- a request-scoped lookup helper, e.g. a tiny cached coroutine `get_default_event_key(transaction)`.

Recommended: add `DEFAULT_EVENT_KEY: str | None = None` to `Settings`. If unset, the redirects controller fetches the slug from the DB on first hit and caches it process-locally (`@lru_cache` on a sync wrapper backed by a one-shot async lookup at app startup, OR a Litestar `on_startup` hook that resolves the slug once and stuffs it into `app.state`).

`DEFAULT_EVENT_SQID` stays for now — the redirects controller in `redirects.py` is rewritten to use the slug version for the new canonical URLs, and remove the sqid-form helper after the migration.

### Templates

Replace `swim(event)` → `event.slug` and `swim(game)` → `game.slug` **only** in templates that produce public links. Audit list:

- `templates/components/AdminSectionCard.html.jinja` — keep sqids (admin links).
- `templates/components/GameCard.html.jinja` — change `/game/{{ swim(game) }}` to `/event/{{ game.event.slug }}/game/{{ game.slug }}` (requires `game.event` selectinload — already present in event_player loaders).
- `templates/components/GameSubmissionRow.html.jinja` — title link to public game page → switch to slug. PUT URLs unchanged.
- `templates/components/ScheduleGameCard.html.jinja` — `_=` on-click navigation to game page → switch to slug.
- `templates/pages/event_games.html.jinja` and other public pages emitting `/event/{...}/...` — switch to slug.
- `templates/pages/game.html.jinja` — any "back to event" link → switch to slug.
- `templates/components/Navigation*.html.jinja` (top-level event nav) — switch to slug.

Sqid-using mutation/htmx links (`hx-put`, `hx-post`, `manage-*`) stay as-is.

### Cross-cutting code references

| File | Current | Change |
|---|---|---|
| `convergence_games/db/models.py` | `class Event(Base):`, `class Game(Base):`, `class User(Base):` | Add `SlugKey` mixin to all three. Override `Game.__table_args__` for composite uniqueness. |
| `convergence_games/db/slugs.py` (new) | — | `generate_unique_slug(session, model, source, scope=None)` helper. |
| `convergence_games/app/exceptions.py` (new or extend `alerts.py`) | — | `SlugRedirect` exception holding canonical path. |
| `convergence_games/app/app_config/exception_handlers.py` | exception handler dict | Register `SlugRedirect` → `Redirect(..., status_code=301)`. |
| `convergence_games/app/routers/frontend/common.py` | `event_with` uses `event_sqid` + `sink` | Accept `event_key`, slug lookup, fallback to sqid + redirect. |
| `convergence_games/app/routers/frontend/event_player.py` | path `/event/{event_sqid:str}/...` | Rename param → `event_key`. Handler signatures unchanged otherwise (dependency still yields `Event`). |
| `convergence_games/app/routers/frontend/game.py` | `path = "/game"`, GET uses `game_sqid` | Add new GET on `/event/{event_key:str}/game/{game_key:str}` scoped lookup. Old GET on `/game/{game_sqid}` only emits a 301 to the canonical path. PUTs remain. |
| `convergence_games/app/routers/frontend/redirects.py` | uses `DEFAULT_EVENT_SQID` | Use default event slug helper. |
| `convergence_games/app/routers/frontend/oauth.py`, `email_auth.py` | `User(...)` constructor sites | Populate `slug` via `generate_unique_slug`. |
| `convergence_games/app/routers/frontend/submit_game.py` | `Game(...)` constructor sites | Populate `slug`. |
| `convergence_games/db/create_mock_data.py`, `convergence_games/services/mock_event.py` (if present) | seeding | Populate slugs for events, games, users. |
| `convergence_games/migrations/versions/<timestamp>_add_slug_columns_to_event_game_user.py` (new) | — | Add columns nullable, backfill, set NOT NULL, add unique constraints/indexes. |
| Public-facing templates (see Templates section) | `swim(event)`, `swim(game)` | `event.slug`, `game.slug`. |

### Migration shape

```python
def upgrade() -> None:
    # 1. add nullable slug columns
    op.add_column("event", sa.Column("slug", sa.String(), nullable=True))
    op.add_column("game", sa.Column("slug", sa.String(), nullable=True))
    op.add_column("user", sa.Column("slug", sa.String(), nullable=True))

    # 2. backfill in Python via op.get_bind() — slugify name/full_name, dedupe with -xxxx suffix
    bind = op.get_bind()
    _backfill_event_slugs(bind)
    _backfill_user_slugs(bind)
    _backfill_game_slugs(bind)  # scoped per event_id

    # 3. NOT NULL + unique constraints/indexes
    op.alter_column("event", "slug", nullable=False)
    op.alter_column("user", "slug", nullable=False)
    op.alter_column("game", "slug", nullable=False)
    op.create_unique_constraint("uq_event_slug", "event", ["slug"])
    op.create_index("ix_event_slug_unique", "event", ["slug"], unique=True)
    op.create_unique_constraint("uq_user_slug", "user", ["slug"])
    op.create_index("ix_user_slug_unique", "user", ["slug"], unique=True)
    op.create_unique_constraint("uq_game_event_slug", "game", ["event_id", "slug"])
    op.create_index("ix_game_event_slug_unique", "game", ["event_id", "slug"], unique=True)
```

The backfill helpers SELECT existing rows, slugify each, track used slugs in an in-memory set (per event for games), and UPDATE.

### Heuristic for sqid vs slug at request time

- Sqids in this app use the default Sqids alphabet which includes uppercase. Slugs are forced lowercase. **Any uppercase char ⇒ treat as sqid.**
- A value with hyphens that is otherwise lowercase ⇒ slug.
- A purely lowercase alphanumeric value with no hyphens ⇒ try slug first (1 query), fall back to sqid decode wrapped in `try/except` (sqid decode of an invalid string returns `[]`, which crashes `[-1]`; catch `IndexError`).

Implement as `_resolve_event(session, event_key)` returning `tuple[Event, bool]` where the bool indicates "matched-via-sqid → caller should redirect".

## Implementation Plan

### Phase 1: Schema + slug helper

- [ ] **Add `SlugKey` mixin to models** (`convergence_games/db/models.py`)
  - Import `from advanced_alchemy.mixins import SlugKey`.
  - Add `SlugKey` to bases of `Event`, `User`.
  - Add `SlugKey` to `Game`; override `__table_args__` with composite `(event_id, slug)` unique constraint and matching unique index, dropping the inherited table-wide ones.
- [ ] **Slug generation helper** (`convergence_games/db/slugs.py` — new)
  - Re-export `slugify` from `advanced_alchemy.utils.text`.
  - Implement `async def generate_unique_slug(session, model, source, *, scope=None) -> str`.
  - Implement `_slug_exists` using `select(exists().where(...))`.
- [ ] **Alembic migration** (`litestar --app convergence_games.app:app database make-migrations -m "add_slug_columns_to_event_game_user"`)
  - Generated skeleton + manual backfill section as designed.
  - Backfill for users: `slugify(f"{first_name} {last_name}".strip())`. Empty fallback `"user"`.
  - Backfill for games: scoped per `event_id`.
  - Add NOT NULL + unique indexes after backfill.
  - Downgrade: drop indexes, constraints, columns.

#### Phase 1 verification

- [ ] `basedpyright` — no new errors
- [ ] `ruff check` — no new errors
- [ ] `litestar database upgrade` runs cleanly on a copy of dev DB
- [ ] All existing rows have non-null, unique slugs (manual SQL spot-check)

### Phase 2: Populate slugs on insert

- [ ] **OAuth user creation** (`convergence_games/app/routers/frontend/oauth.py`)
  - Wherever `User(...)` is instantiated, call `await generate_unique_slug(session, User, f"{user.first_name} {user.last_name}".strip() or "user")` and set `user.slug`.
- [ ] **Email auth user creation** (`convergence_games/app/routers/frontend/email_auth.py`)
  - Same pattern.
- [ ] **Submit-game flow** (`convergence_games/app/routers/frontend/submit_game.py`)
  - On Game insert, call `await generate_unique_slug(session, Game, game.name, scope={"event_id": game.event_id})`.
- [ ] **Mock data + dev seeders** (`convergence_games/db/create_mock_data.py`, `convergence_games/services/mock_event.py` if exists)
  - Populate slugs deterministically (e.g. `slugify(name)`, append `-{i}` on duplicates within an event for tests).
- [ ] **Audit any other insert site** via `grep -rn "Event(\|Game(\|User(" convergence_games/`

#### Phase 2 verification

- [ ] `basedpyright`, `ruff check` clean
- [ ] Dev: register a new user via OAuth → row has slug
- [ ] Dev: submit a new game → row has slug, scoped uniqueness verified by submitting a duplicate name in the same event (should auto-suffix)
- [ ] `pytest` — no regressions

### Phase 3: Public route resolution + sqid redirect

- [ ] **`SlugRedirect` exception + handler** (`convergence_games/app/exceptions.py` or extend `alerts.py`; `convergence_games/app/app_config/exception_handlers.py`)
  - `class SlugRedirect(Exception): def __init__(self, path: str): self.path = path`
  - Handler: `return Redirect(path=exc.path, status_code=301)`.
- [ ] **Update `event_with`** (`convergence_games/app/routers/frontend/common.py`)
  - Rename parameter to `event_key`.
  - Try slug lookup first.
  - Fall back to sqid if `_looks_like_sqid(event_key)` (uppercase present, or no hyphens + decodable).
  - On sqid hit, raise `SlugRedirect` to the slug-canonical URL using `request.app.route_reverse(...)` with the matched handler name and substituted `event_key=event.slug`.
- [ ] **Rename event-scoped route params** (event_player.py, any other controller using `{event_sqid:str}` for **public GETs**: `event_player.py`, `home.py` if present, `redirects.py`)
  - Rename `event_sqid` → `event_key` in path patterns and handler signatures.
  - Manage-* admin paths (`event_manager.py`, `submit_game.py` admin variants) keep `event_sqid` — these are not slug-enabled per scope decision. They continue to call `event_with` only if they're moved to use slugs; if they currently use sqid + `sink` directly, they keep that.
  - **Edge case**: if a manage-* path uses `event_with`, it inherits slug resolution. This is OK — slugs work for admin paths too as a side benefit, but admin templates will keep emitting `swim(event)` (sqid) and the dependency will redirect to the slug. That's a free upgrade — accept it. Alternatively, leave admin URLs un-slugged for now by keeping their dependency pinned to sqid; pick whichever requires fewer changes after grepping `event_with(` callsites.

- [ ] **Game GET routes** (`convergence_games/app/routers/frontend/game.py`)
  - Add a new GET handler at `/event/{event_key:str}/game/{game_key:str}` that:
    - Resolves event via `event_with()`.
    - Resolves game by `(event.id, slug=game_key)`; on miss, falls back to sqid decode like the event resolver and raises `SlugRedirect` to the canonical path.
  - Refactor original GET on `/game/{game_sqid:str}`: become a thin handler that decodes the sqid, looks up the game, and raises `SlugRedirect` to `/event/{game.event.slug}/game/{game.slug}`. Keep PUT handlers (`preference`, `already-played`) on the sqid path untouched.
- [ ] **`route_reverse` handler names**
  - Ensure each public GET handler has a stable `name=` so `request.app.route_reverse("event_games", event_key=...)` works for redirect construction. Add `name=` kwargs where missing.

#### Phase 3 verification

- [ ] `basedpyright`, `ruff check` clean
- [ ] `curl -I http://localhost:8000/event/convergence-2026/games` → 200
- [ ] `curl -I http://localhost:8000/event/<old-sqid>/games` → 301 → `/event/convergence-2026/games`
- [ ] `curl -I http://localhost:8000/game/<old-sqid>` → 301 → `/event/convergence-2026/game/<game-slug>`
- [ ] `curl -I http://localhost:8000/event/convergence-2026/game/dragons-of-doom` → 200
- [ ] `pytest` — no regressions

### Phase 4: Update template links

- [ ] **Public event/game links** in:
  - `templates/components/GameCard.html.jinja`
  - `templates/components/GameSubmissionRow.html.jinja` (title link only)
  - `templates/components/ScheduleGameCard.html.jinja` (`_=` go-to-url)
  - `templates/pages/event_games.html.jinja`
  - `templates/pages/game.html.jinja`
  - Top-level navigation components that emit `/event/{event_sqid}/...`
- [ ] Each location: replace `swim(event)` → `event.slug`, `/game/{{ swim(game) }}` → `/event/{{ game.event.slug }}/game/{{ game.slug }}`. Verify the relevant `selectinload(Game.event)` is already in the query (most public Game queries already load event for date/timezone access — verify in `event_player.py` and `game.py`).
- [ ] Leave admin/htmx mutation links untouched.

#### Phase 4 verification

- [ ] Dev server: load `/`, `/event/convergence-2026/games`, click a game card → URL shows `/event/.../game/...`
- [ ] View page source of games list → all card links use slugs
- [ ] Schedule manager + planner still work (not slug-converted; sqid links function)
- [ ] `npx tsc --noEmit` — TypeScript still clean (no path assumptions baked in)

### Phase 5: Default event + redirects shortcut

- [ ] **Default event slug** (`convergence_games/settings.py`)
  - Optionally add `DEFAULT_EVENT_KEY: str | None = None` env-loadable field.
  - Add an app `on_startup` hook that, if unset, queries the default event and stores `app.state.default_event_key`.
- [ ] **`RedirectsController`** (`convergence_games/app/routers/frontend/redirects.py`)
  - Replace `DEFAULT_EVENT_SQID` references with the default-event slug.
- [ ] **Remove `DEFAULT_EVENT_SQID`** from settings if no remaining callers.

#### Phase 5 verification

- [ ] `curl -I http://localhost:8000/games` → 302 → `/event/convergence-2026/games`
- [ ] `curl -I http://localhost:8000/planner` → 302 → `/event/convergence-2026/planner`
- [ ] `curl -I http://localhost:8000/submit-game` → 302 → `/event/convergence-2026/submit-game`

### Phase 6: Tests

- [ ] **Slug generation unit tests** (`tests/db/test_slugs.py`)
  - `slugify("Convergence 2026")` → `"convergence-2026"`
  - Collision: insert two events with same name → second slug has `-xxxx` suffix
  - Game scoped collision: two games with same name in same event → suffix; two games with same name in different events → both bare slugs
  - User slug from first/last name; empty last name handled
- [ ] **Route resolution tests** (`tests/app/routers/frontend/test_slug_routing.py`)
  - GET `/event/{slug}/games` → 200
  - GET `/event/{old_sqid}/games` → 301 with correct `Location` header
  - GET `/game/{old_sqid}` → 301 to `/event/{event_slug}/game/{game_slug}`
  - GET `/event/{slug}/game/{game_slug}` → 200
  - GET `/event/unknown-slug/games` → 404
  - GET `/game/invalid-sqid` → 404 (not 500)

#### Phase 6 verification

- [ ] `pytest tests/db/test_slugs.py tests/app/routers/frontend/test_slug_routing.py` passes
- [ ] Full `pytest` suite passes

## Acceptance Criteria

- [ ] Type checking passes (`basedpyright`)
- [ ] Linting passes (`ruff check`)
- [ ] All tests pass (`pytest`)
- [ ] TypeScript compiles (`npx tsc --noEmit`)
- [ ] Dev server starts without errors
- [ ] Migration applies cleanly on a copy of production data; every Event, Game, User row has a non-null, scoped-unique slug
- [ ] Public URLs use slugs:
  - `/event/convergence-2026/games`
  - `/event/convergence-2026/game/<some-game-slug>`
  - `/event/convergence-2026/planner`
- [ ] Old sqid URLs return 301 to the canonical slug URL (verified for event and game)
- [ ] HTMX mutation endpoints, manage-* admin pages, party endpoints all continue to function on sqids
- [ ] Submitting a new game whose name collides with an existing game in the same event yields a `-xxxx`-suffixed slug
- [ ] Creating a user via OAuth or email auth populates a slug

## Risks and Mitigations

1. **Slug collision races on simultaneous inserts**: Two requests inserting same-named games concurrently could each generate the bare slug, then second one fails on unique constraint at flush. Mitigation: catch `IntegrityError` on flush in the insert path, regenerate with a suffix, retry once. The transaction provider in `app_config/dependencies.py` already maps `IntegrityError` to 409 — wrap the slug-generating insert in a localised retry before that handler kicks in.
2. **Ambiguous lowercase-only path values**: `abc123` could be either a slug or a sqid. Mitigation: try slug first (cheap unique-indexed lookup); on miss, attempt sqid decode in `try/except IndexError`. Worst case is one extra SELECT for legitimate 404s of slug paths.
3. **Migration backfill on a large `user` table**: User table backfill is O(n) Python-side. Mitigation: chunk via `LIMIT/OFFSET` if row count > 50k; otherwise plain loop is fine for the convention-scale dataset.
4. **Templates referencing `game.event.slug` without loading the relationship**: Could trigger lazy-load errors (`lazy="noload"` is the project default). Mitigation: every public template that emits the new `/event/{event.slug}/game/{game.slug}` URL must be served by a query that `selectinload(Game.event)`. Audit per-template before merging Phase 4.
5. **Slug containing only stripped characters** (e.g. a game named `"???"`): `slugify` returns empty. Mitigation: fallback to `"untitled"` (or class-name + sqid suffix) inside `generate_unique_slug`.

## Notes

- TimeSlot, Party, System, Genre, ContentWarning are deliberately out of scope — TimeSlots appear in URLs only inside admin/planner sub-paths where sqids are fine; the others don't appear in URLs.
- The Advanced Alchemy `SQLAlchemyAsyncSlugRepository` is *not* adopted — the project does not currently use repositories. We use the same algorithm via the `generate_unique_slug` helper instead.
- `swim`/`sink` and `ocean.py` remain — they are still used by all mutation endpoints, party invite codes (uppercase sqids), and admin paths.
- `name=` kwargs on Litestar handlers may need adding for `route_reverse` to work in the redirect builder. Audit during Phase 3.
- Future follow-up (separate task): consider migrating admin paths to slugs for consistency once the public migration is settled.
