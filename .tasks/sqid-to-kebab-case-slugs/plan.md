---
title: Kebab-case slug URLs for public-facing routes
created: 2026-05-07
status: in-progress
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

- `Event`, `Game`, and `User` rows expose a human-readable `slug` column.
- Slugs are auto-generated from a source field and **regenerate when the source changes**.
  - `Event.slug` derived from `Event.name`. Regenerates if `name` is edited.
  - `Game.slug` derived from `Game.name`. Regenerates if `name` is edited.
  - `User.slug` derived from `f"{first_name} {last_name}"` (trimmed if last name empty), populated when profile setup completes (Users have no name at OAuth/email signup time). Regenerates if name fields are edited via the profile page later.
- Until a user has set their name, `User.slug` holds a deterministic placeholder of the form `user-{sqid}` so the column stays NOT NULL and URLs always resolve.
- A rename **breaks the old slug URL** — that is acceptable. Users sharing a freshly-renamed link is uncommon; the sqid-redirect fallback (below) covers anyone with the original sqid URL.
- Slug uniqueness scopes:
  - `Event.slug` and `User.slug`: globally unique (table-wide).
  - `Game.slug`: unique per `event_id` (composite unique constraint).
- On slug collision the Advanced Alchemy default applies: append a 4-char `[a-z0-9]` suffix, e.g. `convergence-2026-x7q3`. When regenerating an existing entity's slug, the entity's own current slug is excluded from the collision check (so a minor name edit that re-slugifies to the same value is a no-op).
- Public-facing GET routes accept slugs as path parameters:
  - `/event/{event_key}` and `/event/{event_key}/games` (event landing + games list)
  - `/event/{event_key}/game/{game_key}` (game info page — moved from top-level `/game/{sqid}`)
  - `/event/{event_key}/planner` and `/event/{event_key}/planner/{time_slot_sqid}` (TimeSlot keeps sqid)
- Admin `manage-*` pages also accept slugs (`/event/{event_key}/manage-schedule`, `manage-submissions`, `manage-players`, `manage-allocation`, `manage-settings`) so admins get readable URLs too.
- Mutation endpoints (PUT/POST/DELETE), HTMX partial endpoints, party lifecycle paths, and OAuth/auth flows continue using sqids unchanged.
- Old sqid URLs for slug-enabled GETs return HTTP 301 to the canonical slug URL — never break a copied sqid link. Old slug URLs after a rename may 404 (acceptable).
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
    exclude_id: int | None = None,
    fallback: str = "untitled",
) -> str:
    base = slugify(source) or fallback
    candidate = base
    while await _slug_exists(session, model, candidate, scope=scope, exclude_id=exclude_id):
        suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
        candidate = f"{base}-{suffix}"
    return candidate
```

`_slug_exists` issues a single `SELECT 1 ... LIMIT 1` filtering by `slug`, any scope keys (e.g. `{"event_id": ...}` for Game), and `model.id != exclude_id` when given. The `exclude_id` parameter is used during regeneration so the entity's own current slug doesn't count as a collision against itself.

A second helper handles the regen-on-rename case:

```python
async def maybe_regenerate_slug(
    session: AsyncSession,
    instance: Base,
    *,
    source: str,
    scope: dict[str, Any] | None = None,
    fallback: str = "untitled",
) -> None:
    desired_base = slugify(source) or fallback
    current = getattr(instance, "slug", None)
    # Already aligned? (current matches desired_base, possibly with a -xxxx suffix retained from prior collision)
    if current == desired_base or (current and current.startswith(f"{desired_base}-") and len(current) == len(desired_base) + 5):
        return
    instance.slug = await generate_unique_slug(
        session,
        type(instance),
        source,
        scope=scope,
        exclude_id=instance.id,
        fallback=fallback,
    )
```

This avoids churning the slug when the slugified form hasn't actually changed (e.g. fixing a typo in description, or capitalisation change in `name` that slugifies the same).

This replicates `SQLAlchemyAsyncSlugRepository.get_available_slug` but works with a plain session, supports scoping, and supports regeneration. We do not need a full Repository class.

### Where slugs are populated and updated

Auto-populate at the route/service layer when an entity is created or its source field is edited — not via SQLAlchemy `before_insert`/`before_update` (those hooks are sync and cannot await a uniqueness check). Touch points:

**Insert sites:**

- `convergence_games/app/routers/frontend/submit_game.py` — when a Game is inserted, call `await generate_unique_slug(session, Game, game.name, scope={"event_id": game.event_id})` and assign before flush. **Also** on the game-edit handler (same controller), call `maybe_regenerate_slug` after applying form changes.
- `convergence_games/app/routers/frontend/oauth.py` — User creation on first OAuth login. User has no name yet — assign placeholder slug `f"user-{swim('User', user.id)}"`. Because we need the row's `id` to mint the placeholder, either: (a) flush the User row, then update its slug and flush again; or (b) generate the placeholder from a UUID-style random token instead of the sqid (e.g. `f"user-{secrets.token_hex(4)}"`). **Recommendation: option (b)** — single insert, no second flush, sqid-style fallback collision-safe via the same `generate_unique_slug` loop.
- `convergence_games/app/routers/frontend/email_auth.py` — Same placeholder pattern.
- `convergence_games/app/routers/frontend/profile.py` — when the user submits the profile-completion form (or edits first/last name later), call `maybe_regenerate_slug(session, user, source=f"{first_name} {last_name}".strip())`. This is the trigger that swaps the placeholder for a real `alice-smith` slug.
- `convergence_games/db/create_mock_data.py` and `convergence_games/services/mock_event.py` (if it creates events/games/users) — populate slugs when seeding.
- Admin Event creation/edit flow (if/when added) — same `maybe_regenerate_slug` pattern.

**Edit/rename sites — call `maybe_regenerate_slug` after applying changes, before commit:**

- Game edit handler in `submit_game.py` (or wherever `Game.name` is mutable).
- Event edit handler in `event_manager.py` (manage-settings) — `await maybe_regenerate_slug(session, event, source=event.name)`.
- User profile edit in `profile.py`.

The HTMX update endpoints often update one column at a time; only re-slug when the source field is in the changeset. Keep this simple: every edit handler that touches `name`/`first_name`/`last_name` calls `maybe_regenerate_slug` unconditionally — the helper short-circuits when the slug is already aligned.

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
| `convergence_games/app/routers/frontend/event_manager.py` | path `/event/{event_sqid:str}/manage-*` | Rename param → `event_key`. Same dependency yields `Event` whether matched by slug or sqid (sqid hit triggers 301). |
| `convergence_games/app/routers/frontend/game.py` | `path = "/game"`, GET uses `game_sqid` | Add new GET on `/event/{event_key:str}/game/{game_key:str}` scoped lookup. Old GET on `/game/{game_sqid}` only emits a 301 to the canonical path. PUTs remain. |
| `convergence_games/app/routers/frontend/redirects.py` | uses `DEFAULT_EVENT_SQID` | Use default event slug helper. |
| `convergence_games/app/routers/frontend/oauth.py`, `email_auth.py` | `User(...)` constructor sites | Populate placeholder `slug` (`user-<random>`) via `generate_unique_slug`. |
| `convergence_games/app/routers/frontend/profile.py` | profile-completion + name-edit handlers | Call `maybe_regenerate_slug(session, user, source=...)` after applying form data. |
| `convergence_games/app/routers/frontend/submit_game.py` | `Game(...)` constructor + game-edit handler | Populate `slug` on insert; call `maybe_regenerate_slug` on edit. |
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
    _backfill_user_slugs(bind)  # placeholder `user-<random>` if first/last name both empty
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

- [x] **Add `SlugKey` mixin to models** (`convergence_games/db/models.py`)
  - Imported `from advanced_alchemy.mixins import SlugKey`.
  - Added `SlugKey` to `Event`, `User`.
  - Added `SlugKey` to `Game`; overrode `__table_args__` with composite `(event_id, slug)` unique constraint and matching unique index, dropping the inherited table-wide ones.
  - Added `before_insert` listener that mints a `<class>-<random>` placeholder slug if none is set — covers tests/seeders/Users-without-name without breaking the NOT NULL constraint. App code overwrites with a meaningful slug via `generate_unique_slug`.
- [x] **Slug generation helper** (`convergence_games/db/slugs.py` — new)
  - Re-exports `slugify` from `advanced_alchemy.utils.text`.
  - `async def generate_unique_slug(session, model, source, *, scope=None, exclude_id=None, fallback="untitled") -> str`.
  - `async def maybe_regenerate_slug(session, instance, *, source, scope=None, fallback="untitled") -> None` — short-circuits when current slug already matches the desired base (or `desired_base-xxxx`).
  - `_slug_exists` uses `select(exists().where(...))`, honours `scope` and `exclude_id`.
- [x] **Alembic migration** (`convergence_games/migrations/versions/2026-05-07_add_slug_columns_to_event_game_user_8d64f1978eda.py`)
  - Adds nullable slug columns first; backfills per the design; alters columns to NOT NULL and adds unique constraints/indexes.
  - User backfill: slugify "first_name last_name", placeholder `user-<random>` when both empty.
  - Game backfill: scoped per `event_id`.
  - Downgrade drops indexes, constraints, columns.

#### Phase 1 verification

- [x] `basedpyright` — no new errors in modified files (0 errors, only Any-related warnings consistent with the rest of the project)
- [x] `ruff check` — clean on modified files
- [x] `pytest` — 28/28 passing (the auth tests that flush Users directly are protected by the placeholder listener)
- [ ] `litestar database upgrade` — not executable in this environment (no docker daemon); migration well-formed and matches the existing migration pattern
- [ ] All existing rows have non-null, unique slugs — verified by inspection of the migration logic; will confirm on first deploy

### Phase 2: Populate and regenerate slugs

- [x] **OAuth/email/sign-up user creation** (`convergence_games/app/common/auth.py`)
  - The User constructor site lives in `_resolve_user_for_intent` (extracted into `_create_user_for_sign_up` for clarity / cyclomatic complexity).
  - When the OAuth/email provider supplies a name, generate a name-based slug immediately. When it doesn't, the `before_insert` placeholder listener mints `user-<random>` and `profile.py` swaps it later.
- [x] **Profile completion / name edits** (`convergence_games/app/routers/frontend/profile.py`)
  - `post_profile` now calls `maybe_regenerate_slug(transaction, db_user, source=f"{first} {last}".strip(), fallback="user")` after applying form data. Swaps placeholder for `alice-smith`, regenerates on subsequent renames.
- [x] **Submit-game create flow** (`convergence_games/app/routers/frontend/submit_game.py`)
  - `post_game` sets `slug=await generate_unique_slug(...)` on the new `Game(...)`.
- [x] **Submit-game edit flow** (`convergence_games/app/routers/frontend/submit_game.py`)
  - `put_game` calls `maybe_regenerate_slug` after assigning `game.name = data.title`.
- [ ] **Event edit flow** (`convergence_games/app/routers/frontend/event_manager.py`)
  - The current `manage-settings` PUT only edits time-span fields, not `Event.name`. No slug regeneration needed today; will add the call when a name-edit handler is introduced.
- [x] **Mock data + dev seeders** (`convergence_games/db/create_mock_data.py`)
  - Set `slug="convergence-2025"` explicitly on the seed Event so dev URLs are deterministic.
- [x] **Audit any other insert/edit site**
  - `grep -rn "Event(\|Game(\|User("` confirmed `auth.py:_create_user_for_sign_up`, `submit_game.py:post_game`, and `create_mock_data.py:create_mock_data` are the only insert sites. Test fixtures construct `User(...)` directly — covered by the placeholder listener.

#### Phase 2 verification

- [x] `basedpyright`, `ruff check` clean — no new errors in modified files
- [x] `pytest` — 28/28 passing
- [ ] Dev verification (register user, edit profile, edit game) — requires running dev server + db; deferred to deploy-time validation

### Phase 3: Public route resolution + sqid redirect

- [x] **`SlugRedirectError` exception + handler** (`convergence_games/app/exceptions.py`, `convergence_games/app/app_config/exception_handlers.py`)
  - `SlugRedirectError(path: str)`. Handler returns `Redirect(path=..., status_code=301)`.
- [x] **Update `event_with`** (`convergence_games/app/routers/frontend/common.py`)
  - Renamed parameter to `event_key: str`.
  - Tries slug first; falls back to sqid via `looks_like_sqid` heuristic; on sqid hit raises `SlugRedirectError` with a path-substitution canonical URL (`/{old_key}/` → `/{new_slug}/`). Avoids `route_reverse` so we don't have to pin handler names.
  - `looks_like_sqid` exported for reuse by `game.py`'s parallel resolver.
- [x] **Rename event-scoped route params** to `event_key` in every controller's path templates:
  - `event_player.py`, `event_manager.py`, `submit_game.py` — all `{event_sqid:str}` → `{event_key:str}` (≈30 sites).
  - Two PUT handlers (`put_player_d20s`, `put_player_compensation`) had `event_sqid: Sqid` parameters; renamed to `event_key: str` and updated `add_transaction_with_delta` accordingly. The endpoint URL emitted in the response template now interpolates the slug-or-sqid path key as-is — slug links produce slug-form HTMX URLs, sqid links produce sqid-form, and the dependency normalises either.
- [x] **Game GET routes** (`convergence_games/app/routers/frontend/game.py`)
  - New `get_game_by_event_and_slug` at `/event/{event_key:str}/game/{game_key:str}` resolves event and game by slug-or-sqid; if either matched via sqid, raises `SlugRedirectError`.
  - Legacy `get_game_legacy` at `/game/{game_sqid:str}` decodes the sqid, looks up the game, and unconditionally redirects to the canonical slug URL.
  - PUT handlers on `/game/{game_sqid:str}/...` unchanged.
- [x] **HX-Redirect URLs** in `event_manager.py` (manage-allocation `/{time_slot_sqid}` redirect, manage-settings PUT response): replaced `swim(event)` with `event.slug` for canonical slug responses.

#### Phase 3 verification

- [x] `basedpyright`, `ruff check` clean — only pre-existing baseline issues remain
- [x] App loads cleanly via `from convergence_games.app.app import app` — all expected `/event/{event_key}/...` and `/event/{event_key}/game/{game_key}` routes register
- [x] Slug helper sanity check: insert two events, second collides → suffix applied (verified end-to-end against SQLite in-memory)
- [x] `pytest` — 28/28 passing
- [ ] curl verification — requires running server; deferred

### Phase 4: Update template links

- [x] **Public game card links** (`GameCard.html.jinja`, `ScheduleGameCard.html.jinja`, `GameSubmissionRow.html.jinja`):
  - `<a href="/game/{swim(game)}">` → `<a href="/event/{game.event.slug}/game/{game.slug}">`
  - `_= go to url ...` navigation in ScheduleGameCard same.
- [x] **Admin manage links** (`AdminSectionCard.html.jinja`, `UserManageRow.html.jinja`):
  - All `/event/{swim(event)}/manage-*` and `/event/{swim(event)}/player/{swim(user)}/...` switched to `event.slug` interpolation.
- [x] **Page-level links** (`event_planner_closed.html.jinja`, `event_games.html.jinja`, `event_session_planner.html.jinja`, `event_manage_settings.html.jinja`, `event_manage_schedule.html.jinja`, `event_manage_allocation.html.jinja`, `my_submissions.html.jinja`, `submit_game_confirmation.html.jinja`, `submit_game.html.jinja`):
  - All `/event/{swim(event)}/...` interpolations switched to `event.slug` (covers anchors and HTMX hx-get/hx-post/hx-put). The path templates accept either slug or sqid via `event_with`, so HTMX endpoints work regardless; using slug keeps URL bar canonical.
- [x] **Submit-game confirmation context**: `post_game` and `put_game` now pass `event` (or `game.event` for the edit case) into the template context so the confirmation page can build the slug-form URL.
- [x] HTMX mutation links to `/game/{sqid}/...` (preference, already-played, /game/{sqid} edit PUT, submission-status) untouched — these routes use the legacy sqid path and `Sqid` parameter validation.
- [x] `data-event="swim(event)"` JS internal identifier in `event_manage_schedule.html.jinja` left as sqid — it's an opaque ID for client-side matching, not a URL.

#### Phase 4 verification

- [x] `pytest` — 28/28 passing
- [x] `ruff check` clean on modified files
- [x] `npx tsc --noEmit` — clean
- [ ] Dev verification (loading pages in a browser) — requires running server; deferred

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
  - User created without name → placeholder `user-xxxxxxxx`
  - `maybe_regenerate_slug` is a no-op when the source slugifies to the existing base
  - `maybe_regenerate_slug` rerolls when source changes (game rename "Foo" → "Bar")
  - `maybe_regenerate_slug` excludes the entity's own current slug from the collision check
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
- [ ] Admin URLs use slugs:
  - `/event/convergence-2026/manage-schedule`, `manage-submissions`, `manage-players`, `manage-allocation`, `manage-settings`
- [ ] Old sqid URLs return 301 to the canonical slug URL (verified for event GETs, manage-* GETs, and game GET)
- [ ] HTMX mutation endpoints and party endpoints continue to function on sqids
- [ ] Submitting a new game whose name collides with an existing game in the same event yields a `-xxxx`-suffixed slug
- [ ] Renaming an Event/Game/User regenerates its slug; minor edits that slugify identically do not
- [ ] Creating a user via OAuth or email auth populates a placeholder `user-xxxxxxxx` slug; completing profile setup with a name swaps it for `firstname-lastname`

## Risks and Mitigations

1. **Slug collision races on simultaneous inserts**: Two requests inserting same-named games concurrently could each generate the bare slug, then second one fails on unique constraint at flush. Mitigation: catch `IntegrityError` on flush in the insert path, regenerate with a suffix, retry once. The transaction provider in `app_config/dependencies.py` already maps `IntegrityError` to 409 — wrap the slug-generating insert in a localised retry before that handler kicks in.
2. **Ambiguous lowercase-only path values**: `abc123` could be either a slug or a sqid. Mitigation: try slug first (cheap unique-indexed lookup); on miss, attempt sqid decode in `try/except IndexError`. Worst case is one extra SELECT for legitimate 404s of slug paths.
3. **Migration backfill on a large `user` table**: User table backfill is O(n) Python-side. Mitigation: chunk via `LIMIT/OFFSET` if row count > 50k; otherwise plain loop is fine for the convention-scale dataset.
4. **Templates referencing `game.event.slug` without loading the relationship**: Could trigger lazy-load errors (`lazy="noload"` is the project default). Mitigation: every public template that emits the new `/event/{event.slug}/game/{game.slug}` URL must be served by a query that `selectinload(Game.event)`. Audit per-template before merging Phase 4.
5. **Slug containing only stripped characters** (e.g. a game named `"???"`): `slugify` returns empty. Mitigation: fallback to `"untitled"` (or class-name + sqid suffix) inside `generate_unique_slug`.
6. **User placeholder leaking into shared URLs**: If an admin shares `/event/.../player/user-7af3b1c2` before the player completes profile setup, then the player completes setup and the slug rolls to `alice-smith`, the old shared URL 404s. Mitigation: this matches the explicit "rename breaks old slug URLs" requirement and is acceptable. Admin player views are scarce on shared links anyway.
7. **Game rename invalidates printed/posted URLs**: Once an event is published, organisers may print the games list with stable URLs. Mitigation: out of scope per the rename-breaks-URLs decision; if it becomes an issue later, add a `slug_history` table or freeze slugs once an event opens for preferences. Note this in `Notes`.

## Notes

- TimeSlot, Party, System, Genre, ContentWarning are deliberately out of scope — TimeSlots appear in URLs only inside admin/planner sub-paths where sqids are fine; the others don't appear in URLs.
- The Advanced Alchemy `SQLAlchemyAsyncSlugRepository` is *not* adopted — the project does not currently use repositories. We use the same algorithm via the `generate_unique_slug` helper instead.
- `swim`/`sink` and `ocean.py` remain — they are still used by all mutation endpoints, party invite codes (uppercase sqids), and admin paths.
- `name=` kwargs on Litestar handlers may need adding for `route_reverse` to work in the redirect builder. Audit during Phase 3.
- Future follow-up (separate task): if rename-breaks-URLs becomes a real-world pain point, introduce a `slug_history` table that records prior slugs and 301-redirects them like the sqid fallback does today. Or freeze slugs at the point an event opens for preferences.
