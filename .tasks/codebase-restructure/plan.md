---
title: Codebase restructure
created: 2026-05-09
status: superseded by design.md + implementation.md (complete)
---

# Codebase Restructure

## Context

Convergence Games is a Litestar web app for managing tabletop RPG convention events. It's server-rendered (Jinja/JinjaX + HTMX), not API-first. The codebase works but has grown organically — business logic is embedded in frontend controllers (`event_manager.py` 1293 lines, `submit_game.py` 745, `event_player.py` 607, `party.py` 585), there's no service layer outside `services/algorithm/` and `services/image/`, raw SQLAlchemy queries are scattered across 16 router files, and code is organized by technical layer rather than by feature domain.

### Reference: litestar-fullstack

The restructure is inspired by [litestar-fullstack](https://github.com/litestar-org/litestar-fullstack/tree/main/src/py/app), which demonstrates:
- Domain-first organization (`domain/accounts/`, `domain/teams/`, etc.)
- Thin controllers delegating to services
- `server/` package with `create_app()` factory, `plugins.py`, `core.py`
- `_underscore.py` private files with `__all__` in `__init__.py`
- One model per file under `db/models/`
- `CompositeServiceMixin` for lazy service composition (not adopted — too CRUD-oriented for our custom queries)
- `SQLAlchemyAsyncRepositoryService` (not adopted — our queries are too complex/custom for generic repos)

### What we're NOT adopting from litestar-fullstack

- **Repository service pattern**: Our queries use aliased subqueries, `with_loader_criteria`, PostgreSQL-specific `insert...on_conflict`, `bindparam` — these don't fit generic CRUD repos
- **DTOs/Schemas layer**: In SSR, output is a template context dict, not serialized DTOs. Input validation already uses Pydantic
- **msgspec**: Keeping Pydantic for form validation
- **Full domain isolation for models**: Models are heavily cross-referenced (User→12+ tables). Splitting into domain-isolated packages would create circular import nightmares. Models stay centralized in `db/models/`
- **CompositeServiceMixin**: Services aren't CRUD-oriented enough to benefit

### What we ARE adopting

- Domain grouping for controllers/services organized by **who uses it** (debug, accounts, user, games, player, admin, public, redirects, system) rather than by entity
- `_underscore.py` private file naming with `__all__` exports
- `server/` package with `create_app()` factory
- Thin controllers → service classes with `AsyncSession` injection
- One model per file

### Design decisions made during planning

- **Domains organized by user role/context**, not entity: `admin` (event managers), `player` (event attendees), `games` (the game entity — both GM submission and public views), `user` (personal pages), `accounts` (auth flows)
- **Game browsing (`/event/{sqid}/games`)** goes in `games` domain, not `player` — it's about the game entity, and the browsing logic lives closer to game queries
- **Preference routes** currently live on `/game/{sqid}` PUT endpoints. Future route like `/preference/{game_sqid}` — can change during player domain service extraction
- **`event_player.py` must split**: game browsing part → `games/_browse.py`, planner part → `player/_planner.py`
- **`game.py` must split**: detail view → `games/_detail.py`, preference/played endpoints → `player/_preferences.py`
- **`event_manager.py` moves as-is** to admin in Phase 3, then splits into 5 controllers + services in Phase 7
- **Services are simple classes** taking `AsyncSession` — no base class, no repository abstraction, no generic CRUD
- **Auth controllers stay as-is** — inherently HTTP-coupled (redirects, cookies, tokens), not worth extracting services
- **`services/algorithm/` and `services/image/`** stay in top-level `services/` — they're cross-cutting, not domain-specific (algorithm may be restructured in future)
- **`ocean.py`** moved to `lib/` (from `db/`) — it's a utility, not a data layer concern
- **`paths.py`** moved to package top-level (from `app/`) — it defines paths relative to the package root

Goal: restructure into `db/domain/lib/server/services/utils` layout, clean server init, split models, then domain-by-domain service extraction. Each phase independently verifiable — app must work after every phase.

## Requirements

- Reorganize into top-level directories: `db/`, `domain/`, `lib/`, `server/`, `services/`, `utils/`, `templates/`, `static/`, `frontend/`
- Domain-based grouping: `debug`, `accounts`, `user`, `games`, `player`, `admin`, `public`, `redirects`, `system`
- Thin controllers delegating to service classes
- One model per file under `db/models/` with `_underscore` naming convention
- `__init__.py` with `__all__` at each package boundary
- `create_app()` factory pattern for server init
- All existing functionality preserved — no route changes, no logic changes
- Auth controllers (`oauth.py`, `email_auth.py`, `profile.py`) stay as-is — no service extraction

## Technical Design

### Target structure

```
convergence_games/
├── server/                    # ASGI app wiring
│   ├── app.py                 # create_app() factory, app = create_app()
│   ├── plugins.py             # Plugin factories (SQLAlchemy, JWT, templates, etc.)
│   └── core.py                # Route registration, domain discovery
├── domain/                    # Feature domains (controllers + services)
│   ├── debug/controllers/     # /debug/*
│   ├── accounts/controllers/  # OAuth, email auth
│   ├── user/controllers/      # /profile, /my-submissions, /settings
│   ├── games/                 # Game entity domain
│   │   ├── controllers/       # browse, detail, submit, search, components
│   │   ├── services/          # game_service, search_service
│   │   └── deps.py
│   ├── player/                # Event participation
│   │   ├── controllers/       # planner, party, preferences
│   │   ├── services/          # party_service, planner_service, preference_service
│   │   └── deps.py
│   ├── admin/                 # Event management
│   │   ├── controllers/       # schedule, submissions, players, allocation, settings
│   │   ├── services/          # schedule_service, allocation_service, player_service
│   │   └── deps.py
│   ├── public/controllers/    # /, /faq
│   ├── redirects/controllers/
│   └── system/controllers/    # health, static, favicon
├── db/
│   ├── models/                # One model per file, _underscore naming
│   ├── enums.py
│   ├── create_mock_data.py
│   └── migrations/
├── lib/                       # Shared utilities (done in Phase 1)
├── services/algorithm/        # Game allocation (stays)
├── services/image/            # Image storage (stays)
├── templates/                 # Moved from app/templates/
├── static/                    # Moved from app/static/
├── frontend/                  # TypeScript source
├── utils/
├── settings.py
└── paths.py
```

### Domain mapping (current controller → new location)

| Current file | Domain | New file(s) | Notes |
|---|---|---|---|
| `debug.py` + `editor_test.py` | debug | `_debug.py` | Merge; route → /debug/editor-test |
| `oauth.py` | accounts | `_oauth.py` | No service extraction |
| `email_auth.py` | accounts | `_email_auth.py` | No service extraction |
| `profile.py` | user | `_profile.py` | |
| `my_submissions.py` | user | `_submissions.py` | |
| `settings.py` | user | `_settings.py` | |
| `submit_game.py` (745 lines) | games | `_submit.py` | Service extraction in Phase 5 |
| `game.py` (194 lines) | games + player | `_detail.py` + `_preferences.py` | Split needed |
| `search.py` | games | `_search.py` | |
| `misc_components.py` | games | `_components.py` | Image upload |
| `event_player.py` (607 lines) | games + player | `_browse.py` + `_planner.py` | Split needed |
| `party.py` (585 lines) | player | `_party.py` | Service extraction in Phase 6 |
| `event_manager.py` (1293 lines) | admin | 5 controllers + services | Phase 7 |
| `home.py` | public | `_public.py` | |
| `redirects.py` | redirects | `_redirects.py` | |
| `health.py` | system | `_health.py` | |
| `static.py`, `favicon.py` | system | `_static.py`, `_favicon.py` | |

### Service pattern

```python
class PartyService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_party(self, time_slot_id: int, user_id: int) -> Party:
        ...
```

DI:
```python
async def provide_party_service(transaction: AsyncSession) -> PartyService:
    return PartyService(transaction)
```

Controller:
```python
class PartyController(Controller):
    dependencies = {"party_service": Provide(provide_party_service)}

    @post(path="/host/{time_slot_sqid:str}")
    async def host_party(self, party_service: PartyService, ...) -> Template:
        party = await party_service.create_party(time_slot_id, user.id)
        return Template(...)
```

No base class, no repository abstraction. Services own their domain's queries and business logic.

### What works well (preserve during restructure)

- **Dependency injection** — clean DI via Litestar: `transaction: AsyncSession`, `user: User`, `image_loader: ImageLoader`
- **Permission system** — type-safe, role-based (`Owner > Manager > Reader > Player`), used as both route guards and template filters
- **Pydantic form validation** — strong typing for forms with cross-field validators
- **`lazy="noload"` on all relationships** — explicit `selectinload()` prevents N+1 queries
- **Sqid encoding** (`lib/ocean.py`) — URL-safe ID obfuscation, salted per model class
- **Image service abstraction** — protocol-based (filesystem/blob), clean interface
- **Algorithm service** — well-encapsulated game allocator with own domain models
- **JinjaX template system** — components auto-receive `request` via passthrough
- **HTMX partial rendering** — `HTMXBlockTemplate` for targeted updates

### What's currently problematic (fix during restructure)

- **Business logic in routers**: event_manager has 350+ lines of allocation orchestration, submit_game has 150+ lines of link-diffing, party has 20 `select()` calls
- **No service layer for most domains**: Direct `select()` → `transaction.execute()` in every route handler
- **Duplicate query patterns**: Same game/event/party loading patterns repeated across files
- **Form validation mixed with persistence**: submit_game's `put_game()` is 150 lines of validation + DB writes interleaved
- **Template rendering details in routes**: HTMX block names, `catalog.render()` calls tightly coupled to handler logic
- **1293-line event_manager.py**: Contains 6 distinct feature areas (schedule, submissions, players, allocation, compensation, settings)

### Key files and their current responsibilities

- `app/app_config/template_config.py` (117 lines) — JinjaX catalog setup, custom filters/globals (swim, user_has_permission, time_range_format, etc.), `catalog` and `jinja_env` used by controllers
- `app/app_config/jwt_cookie_auth.py` (71 lines) — JWT cookie auth, `build_token_extras()` used by auth controllers
- `app/app_config/dependencies.py` (42 lines) — global DI: `provide_transaction`, `provide_user`, `provide_image_loader`
- `app/routers/frontend/__init__.py` (63 lines) — frontend router with `before_request_handler` (profile redirect) and manual controller registration
- `services/algorithm/query_adapter.py` (339 lines) — bridge between DB models and algorithm domain models, `adapt_to_inputs()` / `adapt_results_to_database()`

## Implementation Plan

### Phase 1: Create `lib/` and move shared utilities ✅

- [x] Create `convergence_games/lib/` package
- [x] Move `app/alerts.py` → `lib/alerts.py`
- [x] Move `app/context.py` → `lib/context.py`
- [x] Move `app/events.py` → `lib/events.py`
- [x] Move `app/exceptions.py` → `lib/exceptions.py`
- [x] Move `app/guards.py` → `lib/guards.py`
- [x] Move `app/request_type.py` → `lib/request_type.py`
- [x] Move `app/response_type.py` → `lib/response_type.py`
- [x] Move `app/common/auth.py` → `lib/auth.py`
- [x] Move `permissions/permissions.py` → `lib/permissions.py`
- [x] Move `db/ocean.py` → `lib/ocean.py`
- [x] Move `app/paths.py` → `paths.py` (top-level)
- [x] Create `lib/deps.py` consolidating `event_with`, `game_with`, `party_with`, `time_slot_with`
- [x] Update all import paths across codebase (~45 files)
- [x] Fix pre-existing runtime bug in `request_type.py` (State/Litestar not imported in else branch)
- [x] Update test import path in `tests/app/common/test_auth.py`
- [x] Delete empty `app/common/` directory

#### Phase 1 verification ✅

- [x] `basedpyright` — no new errors (166 pre-existing)
- [x] `ruff check` — no new errors (only pre-existing C901/migration warnings)
- [x] `PYTHONPATH=. pytest tests/` — 28 passed
- [x] App creates successfully (`app = Litestar`, 84 routes)
- [x] Committed: `276be52`

### Phase 2: Create `server/` and refactor app init ✅

- [x] **Create server package** (litestar-fullstack pattern: `app.py`, `core.py`, `plugins.py`):
  - `server/app.py` — `create_app()` factory with lazy imports + `app = create_app()`
  - `server/core.py` — dependencies, exception handlers, sentry init
  - `server/plugins.py` — SQLAlchemy, compression, OpenAPI, HTMX plugin configs
  - `server/__init__.py` — empty (nothing imports from server)
- [x] **Move shared config to `lib/`** (nothing outside server should import from server):
  - `lib/template.py` — JinjaX/Jinja2 template engine, `catalog`, `jinja_env`
  - `lib/auth.py` — merged `jwt_cookie_auth`, `build_token_extras`, auth middleware + existing auth flows
- [x] **Move migrations**: `convergence_games/migrations/` → `convergence_games/db/migrations/`
- [x] **Update migration config**: `script_location` in `alembic.ini` and SQLAlchemy plugin
- [x] **Update entrypoint references**:
  - `convergence_games/__init__.py` — emptied (no re-export due to circular import risk)
  - `convergence_games/app/__init__.py` — emptied (routers still live here for Phase 3)
  - Dockerfile CMD (2 places) → `convergence_games.server.app:app`
  - `scripts/create_all_app_metadata.py` → `convergence_games.server.app` / `server.plugins`
  - `scripts/dump_fixtures.py` → `convergence_games.server.app:app`
- [x] **Update all imports** from `app.app_config.*` → `lib.*`:
  - `catalog` (5 files) → `lib.template`
  - `jinja_env` (1 file) → `lib.template`
  - `jwt_cookie_auth` / `build_token_extras` (3 files) → `lib.auth`
- [x] **Delete**: `app/app.py`, `app/app_config/`, `server/_auth.py`, `server/_template.py`, `server/_dependencies.py`, `server/_exceptions.py`, `server/_sentry.py`
- [x] **Add pyright excludes**: `convergence_games/db/migrations`, `ignore/` (were inflating baseline)

#### Phase 2 verification ✅

- [x] `basedpyright` — 30 errors (no new; baseline reduced by excluding `ignore/` dir)
- [x] `ruff check` — 36 errors (all pre-existing baseline)
- [x] `PYTHONPATH=. pytest tests/` — 28 passed
- [x] App creates with same route count (84)
- [ ] `litestar --app convergence_games.server.app:app run` starts — user tests via VSCode debugger
- [ ] `litestar --app convergence_games.server.app:app database upgrade` — verify when DB available

### Phase 3: Move controllers into domain structure + move templates/static

- [ ] **Create domain directories** with `controllers/__init__.py` for each:
  - `domain/debug/`, `domain/accounts/`, `domain/user/`, `domain/games/`, `domain/player/`, `domain/admin/`, `domain/public/`, `domain/redirects/`, `domain/system/`
- [ ] **Move controllers** (1:1 with `_underscore` naming):
  - `debug.py` + `editor_test.py` → `domain/debug/controllers/_debug.py` (merge)
  - `oauth.py` → `domain/accounts/controllers/_oauth.py`
  - `email_auth.py` → `domain/accounts/controllers/_email_auth.py`
  - `profile.py` → `domain/user/controllers/_profile.py`
  - `my_submissions.py` → `domain/user/controllers/_submissions.py`
  - `settings.py` → `domain/user/controllers/_settings.py`
  - `submit_game.py` → `domain/games/controllers/_submit.py`
  - `search.py` → `domain/games/controllers/_search.py`
  - `misc_components.py` → `domain/games/controllers/_components.py`
  - `party.py` → `domain/player/controllers/_party.py`
  - `event_manager.py` → `domain/admin/controllers/_event_manager.py` (split later in Phase 7)
  - `home.py` → `domain/public/controllers/_public.py`
  - `redirects.py` → `domain/redirects/controllers/_redirects.py`
  - `health.py` → `domain/system/controllers/_health.py`
  - `static.py` → `domain/system/controllers/_static.py`
  - `favicon.py` → `domain/system/controllers/_favicon.py`
- [ ] **Split cross-domain controllers**:
  - `event_player.py` → `domain/games/controllers/_browse.py` (game browsing/filters) + `domain/player/controllers/_planner.py` (session planner)
  - `game.py` → `domain/games/controllers/_detail.py` (detail view) + `domain/player/controllers/_preferences.py` (preference/played endpoints)
- [ ] **Move templates**: `app/templates/` → `convergence_games/templates/`
- [ ] **Move static**: `app/static/` → `convergence_games/static/`
- [ ] **Move TypeScript source**: `app/lib/` → `convergence_games/frontend/`
- [ ] **Update paths**: `paths.py`, `server/plugins.py` template/static config
- [ ] **Update Dockerfile** COPY paths for CSS/JS
- [ ] **Update npm/vite config** for new TS source and output paths
- [ ] **Update `server/core.py`** to import from domain controllers
- [ ] **Delete** `app/routers/`
- [ ] **Write `__init__.py`** for each `controllers/` package with `__all__`

#### Phase 3 verification

- [ ] `basedpyright` — no new errors
- [ ] `ruff check` — no new errors
- [ ] `PYTHONPATH=. pytest tests/` — all pass
- [ ] All routes accessible (84 total)
- [ ] Templates render correctly
- [ ] Static files (CSS/JS) load
- [ ] Dockerfile builds

### Phase 4: Split models — one per file

- [ ] **Create `db/models/` package**
- [ ] **Create `_base.py`**: `Base`, `UserAuditColumns`, `foreign_key_constraint_with_event()`
- [ ] **Create one file per model** (28 files, `_underscore` naming):
  - `_event.py`, `_game.py`, `_game_genre_link.py`, `_game_content_warning_link.py`, `_game_image_link.py`
  - `_game_requirement.py`, `_game_requirement_time_slot_link.py`
  - `_system.py`, `_system_alias.py`, `_genre.py`, `_content_warning.py`, `_image.py`
  - `_time_slot.py`, `_room.py`, `_table.py`, `_session.py`
  - `_party.py`, `_party_user_link.py`
  - `_user.py`, `_user_login.py`, `_user_event_role.py`, `_user_email_verification_code.py`
  - `_user_game_preference.py`, `_user_game_played.py`, `_user_checkin_status.py`
  - `_user_event_d20_transaction.py`, `_user_event_compensation_transaction.py`
  - `_allocation.py`
- [ ] **Create `__init__.py`** re-exporting all models via `__all__`
- [ ] **Keep `@sqla_event.listens_for` handlers** in same file as their model
- [ ] **Delete** old `db/models.py`

#### Phase 4 verification

- [ ] `basedpyright` — no new errors
- [ ] `ruff check` — no new errors
- [ ] `from convergence_games.db.models import Game` still works (zero downstream changes)
- [ ] `litestar database make-migrations` produces no new migration
- [ ] App creates successfully

### Phase 5: Games domain — service extraction

- [ ] **Create `domain/games/services/_game_service.py`**:
  - `create_game(data, user_id, event_id, image_loader)` — system resolution, link creation, image upload
  - `update_game(game, data, image_loader)` — complex link-diffing (~150 lines from submit_game)
  - `update_submission_status(game, status)`
  - `get_game_detail(game_id, user_id_or_none, *options)`
  - Move helpers: `create_if_not_exists()`, `create_new_links()`, `create_image_links()`, `create_image()`
- [ ] **Create `domain/games/services/_search_service.py`**:
  - `search_with_fuzzy_match()` and autocomplete helpers
- [ ] **Create `domain/games/services/__init__.py`** with `__all__`
- [ ] **Thin out controllers**: each handler → parse request, call service, render template
- [ ] **Keep in controllers**: Pydantic form models, validation error handlers, template rendering

#### Phase 5 verification

- [ ] `basedpyright` — no new errors
- [ ] `ruff check` — no new errors
- [ ] Submit new game works
- [ ] Edit existing game (change genres/images/time slots) works
- [ ] Search autocomplete works
- [ ] Game detail view renders

### Phase 6: Player domain — service extraction

- [ ] **Create `domain/player/services/_party_service.py`**:
  - `create_party()`, `join_party()`, `leave_party()`, `promote_member()`, `remove_member()`
  - `check_in()`, `check_out()`
  - `user_is_gm_for_time_slot()`
  - `get_party_for_user()`, `get_allocated_session()`
- [ ] **Create `domain/player/services/_planner_service.py`**:
  - `get_planner_data(event, time_slot_id, user)` — party/preference/tier computation
- [ ] **Create `domain/player/services/_preference_service.py`**:
  - `set_preference(game_id, user_id, rating)`
  - `set_already_played(game_id, user_id, allow_play_again)`
  - `get_user_preferences(event_id, user_id)`
- [ ] **Create `domain/player/services/__init__.py`** with `__all__`
- [ ] **Thin out controllers**

#### Phase 6 verification

- [ ] `basedpyright` — no new errors
- [ ] `ruff check` — no new errors
- [ ] Session planner renders with correct tiers
- [ ] Party: create, join (invite link + QR), leave, promote, remove, check-in/out
- [ ] Preferences: set rating, mark as played

### Phase 7: Admin domain — service extraction

- [ ] **Split `_event_manager.py`** into 5 controllers:
  - `_schedule.py` — `/event/{sqid}/manage-schedule`
  - `_submissions.py` — `/event/{sqid}/manage-submissions`
  - `_players.py` — `/event/{sqid}/manage-players`
  - `_allocation.py` — `/event/{sqid}/manage-allocation`
  - `_settings.py` — `/event/{sqid}/manage-settings`
- [ ] **Create `domain/admin/services/_schedule_service.py`** — schedule CRUD, session management
- [ ] **Create `domain/admin/services/_allocation_service.py`** — run allocation, save results, lock/unlock, apply compensation (~140 lines)
- [ ] **Create `domain/admin/services/_player_service.py`** — player queries, D20/compensation transactions
- [ ] **Create `domain/admin/services/__init__.py`** with `__all__`
- [ ] **Update `admin/controllers/__init__.py`** to export all 5 controllers
- [ ] **Delete** `_event_manager.py`

#### Phase 7 verification

- [ ] `basedpyright` — no new errors
- [ ] `ruff check` — no new errors
- [ ] Schedule: drag sessions, save, check last-updated-by
- [ ] Submissions: sort, filter, approve/reject
- [ ] Players: view balances, add transaction
- [ ] Allocation: run, save, commit, lock/unlock, apply compensation
- [ ] Settings: update event settings

### Phase 8: Cleanup

- [ ] Update `CLAUDE.md` architecture section
- [ ] Update `.claude/rules/` files for new paths
- [ ] Verify Dockerfile builds and runs
- [ ] Clean up any remaining `app/` remnants
- [ ] Ensure `litestar --app` commands in docs point to new entrypoint
- [ ] Remove old `permissions/` directory if still lingering

#### Phase 8 verification

- [ ] All verification from previous phases still passes
- [ ] Documentation matches actual structure

## Acceptance Criteria

- [ ] Type checking passes (`basedpyright`) — no new errors
- [ ] Linting passes (`ruff check`) — no new errors
- [ ] All tests pass (`PYTHONPATH=. pytest tests/`)
- [ ] Dev server starts, all routes accessible
- [ ] Dockerfile builds
- [ ] No business logic in controllers — only request parsing, service calls, template rendering
- [ ] One model per file under `db/models/`
- [ ] Clean domain separation in `domain/`
- [ ] `create_app()` factory pattern in `server/`

## Risks and Mitigations

1. **Circular imports when splitting models**: SQLAlchemy resolves string-based relationship targets lazily. `__init__.py` imports all model modules before mapper config. Mitigation: use string references for all relationships.

2. **Migration path change breaks Alembic**: Update both `alembic.ini` and `SQLAlchemyAsyncConfig.alembic_config.script_location`. Test with `litestar database upgrade` immediately after.

3. **Entrypoint change breaks deployment**: Update Dockerfile CMD, scripts, and any CI/CD references. Test Dockerfile build as part of Phase 2 verification.

4. **event_manager.py allocation logic extraction (Phase 7)**: Most complex queries in codebase — `aliased()`, `with_loader_criteria()`, `transaction.expunge_all()`. Mitigation: extract with zero semantic changes, test every sub-flow.

5. **Template/static path changes break rendering**: Update `paths.py` and all config references. Verify CSS/JS loads and templates render after move.

## Notes

- Phase dependency chain: 1 → 2 → 3 → 4 → 5/6/7 → 8
- Phases 5-7 are independent of each other but sequential is recommended to refine the service pattern
- Auth controllers stay as-is — they're inherently HTTP-coupled (redirects, cookies, tokens)
- `services/algorithm/` and `services/image/` stay in top-level `services/` — they're cross-cutting
- `before_request` profile-redirect hook needs to move to `server/core.py` during Phase 2/3
- No FAQ controller exists yet — slot reserved in public domain for future
- User runs dev server via VSCode debugger — don't launch litestar directly for testing
- Pre-existing type errors (31 in basedpyright after excluding `ignore/` and `db/migrations/`) are baseline — don't try to fix during restructure
- Pre-existing ruff warnings (C901 complexity in event_manager/event_player, N806 aliased vars, migration file lint) are baseline
- `permissions/__init__.py` still exists as a re-export shim pointing to `lib/permissions` — clean up in Phase 8
- Future path renames to consider (breaking URL changes, need template/HTMX updates):
  - `/editor-test` → `/debug/editor-test` (debug route should be under debug prefix)
  - `/components/image-upload` → `/fragments/image-upload` or under `/game/` (generic component endpoint)
  - `/search/*` → `/event/{sqid}/search/*` or keep (search is event-scoped but path doesn't reflect it)
  - PreferencesController and GameController both use `/game` path prefix — works but worth noting

### Codebase stats (pre-restructure baseline)

- Total Python LOC: ~12,000 (excluding migrations)
- 31 SQLAlchemy model classes in `db/models.py` (1013 lines)
- 10+ enum types in `db/enums.py` (567 lines)
- 68 raw `select()` calls scattered across 16 router files
- 0 circular dependencies (clean import graph)
- 84 routes registered
- 28 tests passing

### Import frequency (most-referenced modules, for planning bulk rewrites)

- `db.models` — 22 imports
- `db.enums` — 19 imports
- `lib.response_type` — 16 imports (was `app.response_type`)
- `lib.request_type` — 16 imports (was `app.request_type`)
- `settings` — 14 imports
- `lib.ocean` — 13 imports (was `db.ocean`)
- `lib.guards` — 7 imports (was `app.guards`)
- `app.app_config.template_config` — 6 imports (moves in Phase 2)
- `lib.alerts` — 5 imports (was `app.alerts`)
- `utils.email` — 5 imports
