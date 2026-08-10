# Codebase Restructure (Remaining Phases) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the restructure per `.tasks/codebase-restructure/design.md` — move assets out of `app/`, split `db/models.py` one-model-per-file, extract service classes for games/player/admin domains, split the admin monolith controller, and update docs.

**Architecture:** Behavior-preserving refactor of a Litestar SSR app. Controllers in `apps/frontend/<domain>/controllers/` become thin (request parsing, permission gates, template rendering); business logic and queries move to plain service classes in `apps/frontend/<domain>/services/` holding an `AsyncSession`. No route, logic, or schema changes.

**Tech Stack:** Python 3.13, Litestar, SQLAlchemy async, PostgreSQL, JinjaX/HTMX, uv, basedpyright, ruff, pytest. Frontend: Vite (UMD lib), TailwindCSS v4.

## Global Constraints

- **No route changes, no logic changes, no DB schema changes.** Preserve behavior byte-for-byte, including known quirks (each task lists its own).
- **Baselines (must not regress):** `basedpyright` ~30 pre-existing errors; `ruff check` 36 pre-existing (C901, N806, migration lint); `PYTHONPATH=. uv run pytest tests/` → 28 passed; app exposes 84 routes.
- **Route-count check command:** `PYTHONPATH=. uv run python -c "from convergence_games.server.app import app; print(len(app.routes))"` → `84`.
- **Never launch the dev server** — the user smoke-tests via VSCode debugger. Manual-verification steps are handoffs to the user.
- **Services:** plain classes, `def __init__(self, session: AsyncSession) -> None: self._session = session`. No base class, no repository. Services **never commit or begin transactions** — `provide_transaction` (lib/deps.py:20-28) owns the boundary; services only `add`/`delete`/`flush`/`begin_nested`.
- **Services may** import and use `lib.ocean.swim`/`sink` and raise `lib.alerts.AlertError` (both framework-agnostic). Controllers keep: sqid path-param parsing, `Redirect`/`Template` construction, `request.htmx` branches, permission gates that read `request.user`.
- **DI pattern:** each `_x_service.py` also defines `async def provide_x_service(transaction: AsyncSession) -> XService: return XService(transaction)`. Controllers register via `dependencies = {"x_service": Provide(provide_x_service)}`.
- **File naming:** `_underscore.py` private modules; every package `__init__.py` re-exports with `__all__`.
- **Keep comments** that explain design decisions when moving code; don't add "moved from X" noise.
- **Commits:** plain imperative titles, no Conventional Commits prefixes. Confirm with the user at each commit checkpoint (no-auto-commit convention).
- **No new tests are added** (per approved design): verification = type check + lint + existing suite + app boot + user smoke tests. Existing tests must keep passing untouched.

---

### Task 1: Finish asset moves — templates, static, TypeScript out of `app/` (Phase 3b)

**Files:**
- Move: `convergence_games/app/templates/` → `convergence_games/templates/` (includes co-located `index.ts`, `pages/event_manage_schedule.ts`, `pages/event_manage_allocation.ts`)
- Move: `convergence_games/app/static/` → `convergence_games/static/` (includes gitignored `images/uploads/` tree — `git mv` renames the directory on disk so untracked files come along)
- Move: `convergence_games/app/lib/index.ts`, `editor.ts` → `convergence_games/frontend/`
- Modify: `convergence_games/paths.py`, `vite.config.mts:9,11`, `tsconfig.json:22`, `package.json:4-5`, `Dockerfile:10-11,53-55,65-66`, `.dockerignore:2-4`, `.gitattributes:2-7`, `.vscode/settings.json:137`, `scripts/build_faq.py:35-36`, `README.md:32-40`, `docs/EDITING_FAQ.md:4`
- Delete: `convergence_games/app/` (entire package — `__init__.py` is empty; `app_config/`, `common/`, `routers/` are pycache-only husks)

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `paths.py` constants `TEMPLATES_DIR_PATH`, `COMPONENTS_DIR_PATH`, `STATIC_DIR_PATH` at new locations (same names — consumers `lib/template.py`, `apps/system/_static.py`, `apps/system/_favicon.py`, `services/image/image_loader_from_settings.py` need **no** changes). `APP_DIR_PATH` is deleted (no importers — verified).

- [ ] **Step 1: Move the directories**

```bash
git mv convergence_games/app/templates convergence_games/templates
git mv convergence_games/app/static convergence_games/static
mkdir -p convergence_games/frontend
git mv convergence_games/app/lib/index.ts convergence_games/frontend/index.ts
git mv convergence_games/app/lib/editor.ts convergence_games/frontend/editor.ts
```

Verify untracked uploads came along: `ls convergence_games/static/images/uploads` shows hashed subdirs (`03/`, `b9/`, `f2/`, `f6/`).

No TS import edits needed: `frontend/index.ts` line `export * from "../templates";` still resolves — `frontend/` and `templates/` are siblings under `convergence_games/`, same relative depth as before.

- [ ] **Step 2: Rewrite `convergence_games/paths.py`**

```python
from pathlib import Path

BASE_DIR_PATH = Path(__file__).parent
TEMPLATES_DIR_PATH = BASE_DIR_PATH / "templates"
COMPONENTS_DIR_PATH = TEMPLATES_DIR_PATH / "components"
STATIC_DIR_PATH = BASE_DIR_PATH / "static"
```

- [ ] **Step 3: Update frontend build config**

`vite.config.mts`: `outDir` → `resolve(__dirname, "convergence_games/static/js")`; `lib.entry` → `resolve(__dirname, "convergence_games/frontend")`.

`tsconfig.json:22`: `"include": ["convergence_games/frontend", "convergence_games/templates"]`.

`package.json` lines 4-5: both tailwind script `-o` paths → `./convergence_games/static/css/style.css`.

- [ ] **Step 4: Update Docker + repo metadata paths** (mechanical `convergence_games/app/static` → `convergence_games/static`, `app/templates` → `templates`)

- `Dockerfile` comment lines 10-11, `COPY --from=node-builder` lines 53-55, cache-bust `mv` lines 65-66.
- `.dockerignore` lines 2-4.
- `.gitattributes` lines 2-7 (linguist-vendored JS).
- `.vscode/settings.json:137` — `component_hinting_helper.py` argument → `convergence_games/templates/components/`.
- `scripts/build_faq.py:35-36` — `DEFAULT_INPUT`/`DEFAULT_OUTPUT` → `convergence_games/templates/pages/faq.md` / `faq.html.jinja`.
- `README.md:32-40` and `docs/EDITING_FAQ.md:4` — update the four asset paths.

- [ ] **Step 5: Delete `app/`**

```bash
git rm -r convergence_games/app
rm -rf convergence_games/app   # clears leftover __pycache__ husks
```

- [ ] **Step 6: Rebuild frontend and verify outputs**

```bash
npm run build
ls convergence_games/static/js/lib.js convergence_games/static/css/style.css
```

Expected: build succeeds, both files present at new paths.

- [ ] **Step 7: Run checks**

```bash
uv run basedpyright                    # no new errors vs ~30 baseline
uv run ruff check                      # no new errors vs 36 baseline
PYTHONPATH=. uv run pytest tests/      # 28 passed
PYTHONPATH=. uv run python -c "from convergence_games.server.app import app; print(len(app.routes))"   # 84
grep -rn "convergence_games/app\b\|app/static\|app/templates\|app/lib" --include="*.py" --include="*.json" --include="*.mts" --include="*.toml" --include="Dockerfile" . --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=ignore --exclude-dir=.tasks | grep -v CLAUDE.md | grep -v .claude/rules   # empty (docs rules updated in final task)
```

- [ ] **Step 8: User smoke test (VSCode debugger)** — pages render with CSS, JS features work (editor, sortable), favicons serve, uploaded game images display, `/static/*` files load.

- [ ] **Step 9: Optional but recommended:** `docker build .` succeeds (design lists Dockerfile build as Phase 3b verification).

- [ ] **Step 10: Commit** (confirm with user first)

```bash
git add -A
git commit -m "Move templates, static and TypeScript source out of app/"
```

---

### Task 2: Split `db/models.py` into `db/models/` package (Phase 4)

**Files:**
- Create: `convergence_games/db/models/__init__.py`, `_base.py`, and 28 model files listed below
- Delete: `convergence_games/db/models.py` (1013 lines)

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `from convergence_games.db.models import <AnyModel>` unchanged for all 26 downstream importers. `__all__` = all 30 classes + `Base`, `UserAuditColumns`, `foreign_key_constraint_with_event`.

**Key mechanics:**
- Every model file starts with `from __future__ import annotations` (models.py already has it — line 1).
- Relationship targets already use strings or annotations; SQLAlchemy resolves `Mapped["X"]` forward refs via the class registry at mapper-configuration time, so cross-model *type* references go under `if TYPE_CHECKING:` imports (satisfies basedpyright, avoids cycles).
- **Runtime imports are required** where a class object is used at class-definition time: `secondary=GameGenreLink.__table__` etc. The import direction is entity → link (acyclic). `GameRequirement` uses `secondary="game_requirement_time_slot_link"` and `Party` uses `secondary="party_user_link"` (strings) — no runtime import for those.
- `@sqla_event.listens_for` handlers live in the same file as their model.
- Split the models.py header imports (lines 1-43) per-file to just what each file uses — basedpyright + ruff (F401) will flag mistakes.

- [ ] **Step 1: Create `_base.py`**

Copy from `models.py`: `UserAuditColumns` (lines 46-75), `Base` (78-80), `foreign_key_constraint_with_event()` (329-339). Imports needed: `BigIntAuditBase` from advanced_alchemy, `ForeignKey`, `ForeignKeyConstraint` from sqlalchemy, `Mapped`, `declared_attr`, `mapped_column`, `relationship` from sqlalchemy.orm, `user_id_ctx` from `convergence_games.lib.context`, plus `from __future__ import annotations` and `if TYPE_CHECKING: from ._user import User`.

- [ ] **Step 2: Create the 28 model files** (copy class bodies verbatim from `models.py` at the listed lines; add per-file imports)

| File | Class(es) | models.py lines | Runtime cross-model imports |
|---|---|---|---|
| `_game_genre_link.py` | GameGenreLink | 83-90 | — |
| `_game_content_warning_link.py` | GameContentWarningLink | 93-100 | — |
| `_game_image_link.py` | GameImageLink | 103-109 | — |
| `_image.py` | Image | 112-124 | `GameImageLink` (`secondary=.__table__`) |
| `_event.py` | Event | 128-186 | — |
| `_system.py` | System | 188-197 | — |
| `_system_alias.py` | SystemAlias | 200-207 | — |
| `_genre.py` | Genre | 210-227 | `GameGenreLink` |
| `_content_warning.py` | ContentWarning | 230-247 | `GameContentWarningLink` |
| `_game.py` | Game | 250-326 | `GameGenreLink`, `GameContentWarningLink`, `GameImageLink` |
| `_game_requirement.py` | GameRequirement + `game_requirement_before_insert` listener | 342-396 | — (string secondary) |
| `_game_requirement_time_slot_link.py` | GameRequirementTimeSlotLink + listener | 399-432 | — |
| `_time_slot.py` | TimeSlot | 435-492 | `GameRequirementTimeSlotLink` (`secondary=.__table__`, line 454) |
| `_room.py` | Room | 495-512 | — |
| `_table.py` | Table + `table_before_insert` listener | 515-545 | — |
| `_session.py` | Session | 548-578 | — |
| `_party.py` | Party | 581-602 | — (string secondary) |
| `_party_user_link.py` | PartyUserLink | 605-624 | — |
| `_user_event_d20_transaction.py` | UserEventD20Transaction | 627-681 | — |
| `_user_event_compensation_transaction.py` | UserEventCompensationTransaction | 684-742 | — |
| `_user.py` | User | 745-868 | — |
| `_user_event_role.py` | UserEventRole | 871-884 | — |
| `_user_game_preference.py` | UserGamePreference | 887-920 | — |
| `_user_game_played.py` | UserGamePlayed | 923-938 | — |
| `_user_checkin_status.py` | UserCheckinStatus | 941-956 | — |
| `_user_login.py` | UserLogin | 959-970 | — |
| `_user_email_verification_code.py` | UserEmailVerificationCode | 973-999 | — |
| `_allocation.py` | Allocation | 1002-1013 | — |

Per file: `from __future__ import annotations`; import `Base` (and `foreign_key_constraint_with_event` where the class's `__table_args__` uses it — GameRequirement, GameRequirementTimeSlotLink, Session, Party, and any other user of it: grep `foreign_key_constraint_with_event` in models.py to catch all) from `._base`; import the enums the class references from `convergence_games.db.enums`; put cross-model annotation-only types under `if TYPE_CHECKING:` (e.g. `_game.py` needs `Event`, `System`, `User`, `GameRequirement`, `Session`, `Genre`, `ContentWarning`, `Image`, `UserGamePreference`, `UserGamePlayed` for annotations). Listener files also import `Connection`, `Mapper`, `sqla_event`, `select`/`and_` as their handler bodies require. Preserve section comments (`# Game Information Link Models` etc.) as module docstrings or drop them — do not lose decision-explaining comments inside classes.

- [ ] **Step 3: Create `__init__.py`**

Import every module explicitly and re-export (all mappers must register before first use):

```python
from ._allocation import Allocation
from ._base import Base, UserAuditColumns, foreign_key_constraint_with_event
from ._content_warning import ContentWarning
from ._event import Event
from ._game import Game
from ._game_content_warning_link import GameContentWarningLink
from ._game_genre_link import GameGenreLink
from ._game_image_link import GameImageLink
from ._game_requirement import GameRequirement
from ._game_requirement_time_slot_link import GameRequirementTimeSlotLink
from ._genre import Genre
from ._image import Image
from ._party import Party
from ._party_user_link import PartyUserLink
from ._room import Room
from ._session import Session
from ._system import System
from ._system_alias import SystemAlias
from ._table import Table
from ._time_slot import TimeSlot
from ._user import User
from ._user_checkin_status import UserCheckinStatus
from ._user_email_verification_code import UserEmailVerificationCode
from ._user_event_compensation_transaction import UserEventCompensationTransaction
from ._user_event_d20_transaction import UserEventD20Transaction
from ._user_event_role import UserEventRole
from ._user_game_played import UserGamePlayed
from ._user_game_preference import UserGamePreference
from ._user_login import UserLogin

__all__ = [
    "Allocation",
    "Base",
    "ContentWarning",
    "Event",
    "Game",
    "GameContentWarningLink",
    "GameGenreLink",
    "GameImageLink",
    "GameRequirement",
    "GameRequirementTimeSlotLink",
    "Genre",
    "Image",
    "Party",
    "PartyUserLink",
    "Room",
    "Session",
    "System",
    "SystemAlias",
    "Table",
    "TimeSlot",
    "User",
    "UserAuditColumns",
    "UserCheckinStatus",
    "UserEmailVerificationCode",
    "UserEventCompensationTransaction",
    "UserEventD20Transaction",
    "UserEventRole",
    "UserGamePlayed",
    "UserGamePreference",
    "UserLogin",
    "foreign_key_constraint_with_event",
]
```

- [ ] **Step 4: Delete `models.py`**

```bash
git rm convergence_games/db/models.py
```

- [ ] **Step 5: Verify mappers configure and imports hold**

```bash
PYTHONPATH=. uv run python -c "
from convergence_games.db import models
from sqlalchemy.orm import configure_mappers
configure_mappers()
print('mappers OK', len(models.Base.registry.mappers))
"
```

Expected: `mappers OK 30`, no `InvalidRequestError`.

- [ ] **Step 6: Verify no-op migration** (requires dev DB: `docker compose -f compose.dev.yaml up -d`, then `litestar --app convergence_games.server.app:app database upgrade` to be current)

```bash
litestar --app convergence_games.server.app:app database make-migrations -m "should be empty"
```

Expected: no changes detected / empty migration. If a file is generated, inspect it — an empty `upgrade()` confirms parity; delete the generated file either way.

- [ ] **Step 7: Run checks** (same four commands as Task 1 Step 7; also `uv run ruff format` the new package)

- [ ] **Step 8: Commit** (confirm with user first)

```bash
git add -A
git commit -m "Split db/models.py into one model per file"
```

---

### Task 3: Games services package + SearchService (Phase 5, part 1)

**Files:**
- Create: `convergence_games/apps/frontend/games/services/__init__.py`, `convergence_games/apps/frontend/games/services/_search_service.py`
- Modify: `convergence_games/apps/frontend/games/controllers/_search.py`

**Interfaces:**
- Consumes: models re-exports from Task 2 (works identically pre-split).
- Produces: `SearchService` with `fuzzy_search`, `search_visible_to_user`, `get_by_id`; `SearchResult[T]` dataclass and `type SearchableBase = System | Genre | ContentWarning` alias — all importable from `convergence_games.apps.frontend.games.services`. `provide_search_service` factory. Task 4-6 will extend the same `services/` package.

- [ ] **Step 1: Create `_search_service.py`**

Move from `_search.py`: the `SearchableBase` alias (line 23), `SearchResult` dataclass (26-31), and `search_with_fuzzy_match` (34-101) → method `fuzzy_search`, dropping the `transaction` param in favor of `self._session` and making `suggested_on_empty` keyword-only (call sites already comply):

```python
class SearchService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def fuzzy_search[T: SearchableBase](
        self,
        model_type: type[T],
        search: str,
        extra_filters: ColumnExpressionArgument[bool] | None = None,
        *,
        suggested_on_empty: bool = False,
    ) -> list[SearchResult[T]]:
        ...  # body = _search.py lines 42-101 verbatim, transaction -> self._session

    async def search_visible_to_user[T: SearchableBase](
        self,
        model_type: type[T],
        search: str,
        user_id: int | None,
        *,
        suggested_on_empty: bool = False,
    ) -> list[SearchResult[T]]:
        # absorbs the triplicated filter construction at _search.py 122-125 / 166-169 / 212-217:
        # (submission_status == APPROVED) OR (created_by == user_id when user_id is not None),
        # then delegates to fuzzy_search
        ...

    async def get_by_id[T: SearchableBase](self, model_type: type[T], id_: int) -> T | None:
        return await self._session.get(model_type, id_)


async def provide_search_service(transaction: AsyncSession) -> SearchService:
    return SearchService(transaction)
```

(`search_visible_to_user` is safe generically: `submission_status` exists on System/Genre/ContentWarning — models.py 191/214/234 — and `created_by` is on the `UserAuditColumns` mixin.)

- [ ] **Step 2: Create `services/__init__.py`**

```python
from ._search_service import SearchableBase, SearchResult, SearchService, provide_search_service

__all__ = [
    "SearchResult",
    "SearchService",
    "SearchableBase",
    "provide_search_service",
]
```

- [ ] **Step 3: Thin `_search.py`**

- Add `dependencies = {"search_service": Provide(provide_search_service)}` to `SearchController`.
- The three `*_search_results` handlers (120-135, 164-179, 208-227) each become: `results = await search_service.search_visible_to_user(Model, search, request.user.id if request.user else None, suggested_on_empty=...)` + their existing template call. Genre and ContentWarning keep `suggested_on_empty=True`; System omits it.
- The three `*_search_selected` handlers use `await search_service.get_by_id(Model, sink(sqid))`; keep the three distinct `NotFoundException` detail strings in the controller.
- `get_search` (107-118) and the three `*_search_new` handlers stay untouched (no DB, no logic).
- Delete the moved alias/dataclass/function from the controller; import `SearchService, provide_search_service` from `..services`. Note: `templates/components/forms/search/SearchResultsList.html.jinja:3` annotates `results: list[SearchResult]` — annotation only, no import; no template change needed.

- [ ] **Step 4: Run checks** (Task 1 Step 7 commands — baselines hold, 84 routes)

- [ ] **Step 5: User smoke test** — in game submit form: system autocomplete, genre autocomplete (empty search shows suggested), content-warning autocomplete, selecting existing + "new:" entries.

- [ ] **Step 6: Commit** (confirm with user first): `git commit -m "Extract SearchService from search controller"`

---

### Task 4: GameService — creation path (Phase 5, part 2)

**Files:**
- Create: `convergence_games/apps/frontend/games/services/_game_service.py`
- Modify: `convergence_games/apps/frontend/games/controllers/_submit.py`, `convergence_games/apps/frontend/games/services/__init__.py`

**Interfaces:**
- Consumes: `services/` package from Task 3.
- Produces: `GameService` with `get_or_create_by_name`, `build_new_links`, `create_image`, `build_image_links`, `create_game`; `provide_game_service`. Task 5 adds the update methods to this same class; Task 6 adds detail methods.

**Preserve verbatim:** `create_if_not_exists` returns a *transient, un-added* instance when missing (persistence via relationship cascade); `build_image_links` assigns `sort_order=i` from the enumerate index over the **unfiltered** `data.image` list (line 339); blob upload in `create_image` happens before any DB flush (orphaned-blob-on-rollback behavior stays); `create_game` ends with `flush()` + `refresh()` (the template sqids the new id).

- [ ] **Step 1: Create `_game_service.py` with the creation-path methods**

```python
class GameService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create_by_name[T: System | Genre | ContentWarning](
        self, model_type: type[T], name: str
    ) -> T:
        ...  # body = _submit.py 276-285 verbatim (transaction -> self._session)

    async def build_new_links(
        self, *, data: SubmitGameForm, game: Game
    ) -> tuple[list[GameGenreLink], list[GameContentWarningLink], list[GameRequirementTimeSlotLink]]:
        ...  # body = _submit.py 288-316; create_if_not_exists calls -> self.get_or_create_by_name

    async def create_image(self, upload_file: UploadFile, image_loader: ImageLoader) -> Image:
        ...  # body = _submit.py 319-325 (no session use; kept here for cohesion)

    async def build_image_links(
        self, *, data: SubmitGameForm, game: Game, image_loader: ImageLoader
    ) -> list[GameImageLink]:
        ...  # body = _submit.py 328-341

    async def create_game(
        self, *, data: SubmitGameForm, event: Event, gamemaster_id: int, image_loader: ImageLoader
    ) -> Game:
        ...  # body = _submit.py 453-507: system resolution (453-457), Game + GameRequirement
             # construction (459-486) with gamemaster_id param replacing request.user.id,
             # build_new_links + build_image_links (488-498), add/add_all (500-504),
             # flush + refresh (506-507). Returns the refreshed Game.


async def provide_game_service(transaction: AsyncSession) -> GameService:
    return GameService(transaction)
```

`SubmitGameForm` stays defined in `_submit.py`; the service imports it from the controller module (`from ..controllers._submit import SubmitGameForm`) **would create a cycle** (controller imports service). Instead move `NewValue`, `SqidOrNew`, `make_sqid_or_new_validator` (62-84) and `SubmitGameForm` (95-223) into a new sibling `apps/frontend/games/_forms.py` module, imported by both controller and service. Export nothing from it in packages' `__all__` (internal module).

- [ ] **Step 2: Update `services/__init__.py`** — add `GameService`, `provide_game_service` to imports and `__all__`.

- [ ] **Step 3: Thin `post_game` in `_submit.py`** (body 438-514)

Handler keeps: `assert request.user is not None` (446), submissions-open/permission gate raising `AlertError` (448-451), and the `HTMXBlockTemplate` render (509-514). Middle becomes:

```python
new_game = await game_service.create_game(
    data=data, event=event, gamemaster_id=request.user.id, image_loader=image_loader
)
```

Add `dependencies = {"game_service": Provide(provide_game_service)}` on `SubmitGameController`. Delete the moved module-level helpers (276-341) from `_submit.py`; `get_submit_game`/`get_edit_game` are untouched.

- [ ] **Step 4: Run checks** (baselines, 84 routes)

- [ ] **Step 5: User smoke test** — submit a brand-new game with new system ("new:"), new + existing genres, content warnings, time slots, and an image upload; confirmation page shows the game.

- [ ] **Step 6: Commit** (confirm with user first): `git commit -m "Extract GameService creation path from submit controller"`

---

### Task 5: GameService — update path + submission status (Phase 5, part 3)

**Files:**
- Modify: `convergence_games/apps/frontend/games/services/_game_service.py`, `convergence_games/apps/frontend/games/controllers/_submit.py`

**Interfaces:**
- Consumes: `GameService` from Task 4.
- Produces: `GameService.update_game`, `GameService.set_submission_status`.

**Preserve verbatim (do NOT fix during extraction):**
- The `new:`-name-already-exists path (590/614): resolved persisted objects never match the `link.genre_id` int comparison, producing a delete+insert of the same link pair in one flush. Known latent quirk — keep it.
- Image-link `else` branch reassigns `sort_order = desired.index(image_link.image_id)` for surviving links (664-666).
- Int-vs-object add branches: int branch dedupes, object branch doesn't (598-608, 622-638, 668-680).
- `put_game` never flushes/refreshes (asymmetric with `create_game`).
- Comments at 570-571 explaining gamemaster/event deliberately not updated — keep them.

- [ ] **Step 1: Add update methods to `GameService`**

```python
    async def update_game(self, *, game: Game, data: SubmitGameForm, image_loader: ImageLoader) -> Game:
        """Precondition: game loaded with genre_links, content_warning_links, image_links,
        and game_requirement.time_slot_links (the game_with dep at _submit.py 524-533)."""
        self._apply_scalar_fields(game, data)
        await self._apply_system(game, data)
        await self._sync_genre_links(game, data)
        await self._sync_content_warning_links(game, data)
        await self._sync_time_slot_links(game, data)
        await self._sync_image_links(game, data, image_loader)
        self._session.add(game)
        return game

    def _apply_scalar_fields(self, game: Game, data: SubmitGameForm) -> None:   # 555-565 + 573-582 (sync)
    async def _apply_system(self, game: Game, data: SubmitGameForm) -> None:    # 566-571 incl. comments
    async def _sync_genre_links(self, game: Game, data: SubmitGameForm) -> None:            # 589-608
    async def _sync_content_warning_links(self, game: Game, data: SubmitGameForm) -> None:  # 611-638
    async def _sync_time_slot_links(self, game: Game, data: SubmitGameForm) -> None:        # 641-654
    async def _sync_image_links(self, game: Game, data: SubmitGameForm, image_loader: ImageLoader) -> None:  # 657-680

    async def set_submission_status(self, game: Game, submission_status: SubmissionStatus) -> Game:
        game.submission_status = submission_status
        self._session.add(game)                                                  # 713-714
        return game
```

Bodies verbatim from the listed `_submit.py` lines; `create_if_not_exists`/`create_image` calls → `self.get_or_create_by_name`/`self.create_image`. Do NOT genericize genre/CW sync in this task (candidate follow-up, out of scope).

- [ ] **Step 2: Thin `put_game`** — keeps assert (546), editing-open/permission gate (548-551), then `game = await game_service.update_game(game=game, data=data, image_loader=image_loader)`, then render (684-689). The `# noqa: C901` on `put_game` should now be removable — check `ruff check` (the complexity moved to the service; if any `_sync_*` method trips C901 there, keep a targeted noqa on that method only).

- [ ] **Step 3: Thin `put_game_submission_status`** — keeps assert (711) + `catalog.render` block (716-722); middle becomes `game = await game_service.set_submission_status(game, data.submission_status)`.

- [ ] **Step 4: Run checks** (baselines, 84 routes)

- [ ] **Step 5: User smoke test** — edit an existing game: change scalars, swap genres (remove one/add one/add "new:"), change content warnings, change time slots, reorder + add + remove images; approve/reject from submissions row.

- [ ] **Step 6: Commit** (confirm with user first): `git commit -m "Extract GameService update path from submit controller"`

---

### Task 6: GameService — detail path (Phase 5, part 4)

**Files:**
- Modify: `convergence_games/apps/frontend/games/services/_game_service.py`, `convergence_games/apps/frontend/games/controllers/_detail.py`

**Interfaces:**
- Consumes: `GameService` from Tasks 4-5.
- Produces: `GameService.get_game_for_detail`, `get_user_game_context` (+ `UserGameContext` dataclass), `get_scheduled_sessions`, `get_game_image_urls`.

- [ ] **Step 1: Add detail methods to `GameService`** (source: `_detail.py`)

```python
@dataclass(slots=True)
class UserGameContext:
    preference: UserGamePreference | None
    user_game_played: UserGamePlayed | None
    has_d20: bool


class GameService:
    ...
    async def get_game_for_detail(self, game_id: int) -> Game | None:
        ...  # _detail.py 33-47: SELECT Game with the 7 selectinloads, scalar_one_or_none

    async def get_user_game_context(self, *, game_id: int, user_id: int, event_id: int) -> UserGameContext:
        ...  # _detail.py 52-78 (three sequential queries) + the has_d20 predicate from line 119
             # (latest is not None and latest.current_balance > 0)

    async def get_scheduled_sessions(self, game_id: int) -> list[Session]:
        ...  # _detail.py 92-108 + the sorted(..., key=lambda s: s.time_slot.start_time) from line 118

    async def get_game_image_urls(self, game: Game, image_loader: ImageLoader) -> list[dict[str, str]]:
        ...  # _detail.py 84-90: full + size=300 thumbnail paths
```

(Check the exact field types at `_detail.py:52-78` when moving — the dataclass fields mirror what the template context received.) The anonymous-user branch (79-82) is equivalent to `UserGameContext(None, None, False)` — construct that in the controller's `else`.

- [ ] **Step 2: Thin `get_game` in `_detail.py`** — keeps `sink(game_sqid)` (32), the `HTTPException(404)` (49-50, stays a raw `HTTPException`, not `NotFoundException`), the authed/anonymous branch calling `get_user_game_context` vs default, and the `Template` render with `block_name=request.htmx.target`. Context dict becomes straight field copies (no inline `sorted`/predicate — those moved into the service).

- [ ] **Step 3: Run checks** (baselines, 84 routes)

- [ ] **Step 4: User smoke test** — game detail page: logged out and logged in, image gallery, scheduled sessions listed in start-time order, preference slider state, "already played" state, d20 indicator.

- [ ] **Step 5: Commit** (confirm with user first): `git commit -m "Extract GameService detail path from game controller"`

---

### Task 7: Player services package + PreferenceService (Phase 6, part 1)

**Files:**
- Create: `convergence_games/apps/frontend/player/services/__init__.py`, `convergence_games/apps/frontend/player/services/_preference_service.py`
- Modify: `convergence_games/apps/frontend/player/controllers/_preferences.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `PreferenceService` with `get_event_for_game`, `set_game_preference`, `set_game_already_played`; `provide_preference_service`. Tasks 8-9 extend this `services/` package.

**Preserve:** `put_game_already_played` has **no** open-check/permission gate (asymmetric with `put_game_preference`) — keep asymmetric.

- [ ] **Step 1: Create `_preference_service.py`**

```python
class PreferenceService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_event_for_game(self, game_id: int) -> Event | None:
        ...  # _preferences.py 37-39: SELECT Event JOIN Game WHERE Game.id == game_id

    async def set_game_preference(
        self, *, user_id: int, game_id: int, rating: UserGamePreferenceValue
    ) -> UserGamePreference:
        ...  # _preferences.py 44-56: SELECT UserGamePreference (game, user, frozen_at_time_slot_id IS NULL);
             # create if missing; set .preference; session.add

    async def set_game_already_played(
        self, *, user_id: int, game_id: int, allow_play_again: bool
    ) -> UserGamePlayed:
        ...  # _preferences.py 68-79: same upsert shape for UserGamePlayed


async def provide_preference_service(transaction: AsyncSession) -> PreferenceService:
    return PreferenceService(transaction)
```

- [ ] **Step 2: Create `services/__init__.py`** exporting `PreferenceService`, `provide_preference_service` with `__all__`.

- [ ] **Step 3: Thin `_preferences.py`** — controller keeps `sink()` (35, 67), the preferences-open/permission gate (40-42, now using `event = await preference_service.get_event_for_game(game_id)`), and the `Response(content="", status_code=204)` returns. Register `preference_service` dependency on `PreferencesController`.

- [ ] **Step 4: Run checks** (baselines, 84 routes)

- [ ] **Step 5: User smoke test** — on a game detail/browse page set a preference rating (expect 204/no visual error), toggle already-played + allow-play-again.

- [ ] **Step 6: Commit** (confirm with user first): `git commit -m "Extract PreferenceService from preferences controller"`

---

### Task 8: PartyService (Phase 6, part 2)

**Files:**
- Create: `convergence_games/apps/frontend/player/services/_party_service.py`
- Modify: `convergence_games/apps/frontend/player/controllers/_party.py`, `convergence_games/apps/frontend/player/services/__init__.py`

**Interfaces:**
- Consumes: player `services/` package from Task 7.
- Produces: `PartyService` (methods below), `PartyOverview` dataclass, `provide_party_service`. `PlannerService` (Task 9) does NOT depend on this.

**Preserve verbatim (load-bearing quirks):**
- `transaction.expunge_all()` (`_party.py:97`) position: after the party/checkin/is_gm/max-size queries, before the allocation query. It detaches the DI-injected `user`/`time_slot` too — same session, same effect from inside the service.
- `await flush()` after party insert (192) — the follow-up overview request needs the row.
- `begin_nested()` savepoint in promote (410-417) — demote-flush-promote must stay one method (dodges `ix_unique_party_leader`).
- `leave_party` deletes the whole party whenever the **leader** leaves (321-327), despite its comment saying "only member" — keep code AND comment as-is.
- `gm_index` list-comp `[0]` (125-131) raises `IndexError` if the GM isn't among allocated players — keep the expression.
- `join_party` re-queries `TimeSlot` (234-236, 260-262) purely for redirect URLs, and reads max size off `party.time_slot.event` (270) while `get_overview` uses a dedicated scalar query (93-95) — keep both paths, do not unify.
- Dead `selectinload(PartyUserLink.user)` at 401-403 / 460-462 — keep for parity.

- [ ] **Step 1: Create `_party_service.py`**

```python
@dataclass(slots=True)
class PartyOverview:
    party: Party | None
    leader_id: int | None
    checked_in: bool
    is_gm: bool
    max_party_size: int | None
    allocated_session: Session | None
    allocated_session_players: list[User]


class PartyService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def user_is_gm_for_time_slot(self, *, user_id: int, time_slot_id: int) -> bool:
        ...  # module-level fn at _party.py 34-46, verbatim

    async def get_overview(self, *, user: User, time_slot: TimeSlot) -> PartyOverview:
        ...  # _party.py 62-134 in original order: party query (62-80), checked_in (81-87),
             # is_gm (88), leader_id derivation (89-92), max_party_size (93-95),
             # expunge_all (97), allocation query (98-116), player ordering (117-134)

    async def host_party(self, *, user_id: int, time_slot_id: int) -> Party:
        ...  # _party.py 169-192: GM check -> AlertError, existing-party check -> AlertError,
             # insert Party + leader PartyUserLink, flush

    async def join_party(self, *, user_id: int, time_slot_id: int, invite_id: int) -> Party:
        ...  # _party.py 220-284 verbatim, including the TimeSlot re-queries and
             # swim()-built redirect_url AlertErrors (service may use swim/AlertError)

    async def leave_party(self, *, user_id: int, time_slot_id: int) -> None:
        ...  # _party.py 310-327

    async def get_party_with_members(self, *, user_id: int, time_slot_id: int) -> Party | None:
        ...  # _party.py 344-351; the two AlertErrors (353-354 warning, 356-363 member-name
             # info string) STAY in the controller — presentation

    async def promote_member(self, *, user_id: int, time_slot_id: int, member_id: int) -> None:
        ...  # _party.py 384-417 (leadership check, target lookup, begin_nested swap)

    async def remove_member(self, *, user_id: int, time_slot_id: int, member_id: int) -> None:
        ...  # _party.py 442-469 (self-removal rejection, leadership check, target lookup, delete)

    async def check_in(self, *, user_id: int, time_slot_id: int, checkin_open_time: dt.datetime | None) -> None:
        ...  # _party.py 491-492 open-time check -> AlertError, then _set_checkin_status(True)

    async def check_out(self, *, user_id: int, time_slot_id: int) -> None:
        ...  # _set_checkin_status(False)

    async def _set_checkin_status(self, *, user_id: int, time_slot_id: int, checked_in: bool) -> None:
        ...  # _party.py 494-507 == 529-542: select-then-update-or-insert upsert


async def provide_party_service(transaction: AsyncSession) -> PartyService:
    return PartyService(transaction)
```

- [ ] **Step 2: Update `services/__init__.py`** — add `PartyOverview`, `PartyService`, `provide_party_service`.

- [ ] **Step 3: Thin `_party.py`** — every handler keeps: `time_slot is None` guard, `status != PRE_ALLOCATION` redirect, `sink`/`sink_upper` parsing (join 245-248 stays in controller as request parsing — pass the decoded `invite_id` int), `request.htmx` branch (286-290), all `Redirect(...)` construction, `overview_party`'s render block (136-149) fed from `PartyOverview` fields, and `get_party_members`' two AlertErrors. Delete module-level `user_is_gm_for_this_time_slot`. Register `party_service` dependency on `PartyController`. `join_empty_party` (196-198) untouched.

- [ ] **Step 4: Run checks** (baselines, 84 routes)

- [ ] **Step 5: User smoke test** — party overview (with and without party), host, join via invite link + QR, join-full/join-again error alerts, leave (as member; as leader — party dissolves), member list alert, promote, remove, check-in before/after open time, check-out.

- [ ] **Step 6: Commit** (confirm with user first): `git commit -m "Extract PartyService from party controller"`

---

### Task 9: PlannerService (Phase 6, part 3)

**Files:**
- Create: `convergence_games/apps/frontend/player/services/_planner_service.py`
- Modify: `convergence_games/apps/frontend/player/controllers/_planner.py`, `convergence_games/apps/frontend/player/services/__init__.py`

**Interfaces:**
- Consumes: player `services/` package.
- Produces: `PlannerService.get_planner_data(*, event, user, time_slot_id) -> PlannerData`; `provide_planner_service`.

**Preserve verbatim:**
- Scheduled-sessions query (170-177) is **globally unfiltered** by event — keep.
- Tier override ordering is a strict if/elif chain: GM > already-played > age-restricted > d20-downgrade; `downgraded_d20` flips only when the caller IS the leader (213-222).
- Missing leader preference defaults to `UserGamePreferenceValue.D6` before tiering.
- Row tuple access `.t[0]`/`.t[1]` (109-117, 183): if converted to named unpacking inside the service, convert all five sites together.

- [ ] **Step 1: Create `_planner_service.py`**

```python
@dataclass(slots=True)
class PlannerData:  # exactly the template context values built at _planner.py 233-246
    selected_time_slot: TimeSlot
    game_tier_list: list[tuple[TierValue, list[Game]]]
    preferences: dict[int, UserGamePreferenceValue]
    user_game_playeds: dict[int, UserGamePlayed]
    party_leader: User
    all_party_members_over_18: bool
    scheduled_time_slots: dict[int, list[int]]
    has_d20: bool
    all_party_members_have_d20: bool
    any_party_member_has_played_and_wont_repeat: set[int]
    downgraded_d20: bool


class PlannerService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_planner_data(self, *, event: Event, user: User, time_slot_id: int | None) -> PlannerData:
        ...  # _planner.py 62-228 in original order:
             # time-slot resolve from event.time_slots + future-slot fallback (62-75),
             # latest d20 transaction (77-85), aliased party-member query (87-107),
             # leader/over-18/has-d20 derivation incl. partyless fallback (108-123),
             # main Game+Session+preference statement with conditional leader join (125-169),
             # global scheduled sessions fold (170-177), played-games query (179-199),
             # tier computation (201-228). has_d20 predicate from line 242 computed here.
```

(Verify the exact `TierValue` import/location when moving — it's used at line 88's aliases block and the tier computation; also move/import the four `aliased()` constructs as-is.) Keep it one method: the intermediate structures (`PartyContext` etc.) are internal locals; don't introduce extra dataclasses beyond `PlannerData` (YAGNI — nothing else calls these pieces).

- [ ] **Step 2: Update `services/__init__.py`** — add `PlannerData`, `PlannerService`, `provide_planner_service`.

- [ ] **Step 3: Thin `_planner.py`** — controller keeps: planner-open/permission check + closed-page render (53-60), `sink(time_slot_sqid)` (64), and the `HTMXBlockTemplate` render (230-247) whose context is now straight `PlannerData` field copies. Register `planner_service` dependency.

- [ ] **Step 4: Run checks** (baselines, 84 routes)

- [ ] **Step 5: User smoke test** — planner with/without party, with/without d20 (D20→D12 downgrade shows), GM game pinned to GM tier, already-played tier, R18 game with under-18 party member, time-slot switcher, closed-planner page as non-manager.

- [ ] **Step 6: Commit** (confirm with user first): `git commit -m "Extract PlannerService from planner controller"`

---

### Task 10: Split `_event_manager.py` into 5 controllers (Phase 7, part 1 — pure move, no service extraction)

**Files:**
- Create: `convergence_games/apps/frontend/admin/_common.py`, `convergence_games/apps/frontend/admin/controllers/_schedule.py`, `_submissions.py`, `_players.py`, `_allocation.py`, `_settings.py`
- Modify: `convergence_games/apps/frontend/admin/controllers/__init__.py`, `convergence_games/apps/frontend/__init__.py` (route_handlers list, line 44 area)
- Delete: `convergence_games/apps/frontend/admin/controllers/_event_manager.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `ScheduleController`, `SubmissionsController`, `PlayersController`, `AllocationController`, `SettingsController` (exported from `controllers/__init__.py`); `apps/frontend/admin/_common.py` with `SqidInt` and `user_can_manage_submissions(user, event) -> bool`. Tasks 11-13 thin these controllers.

**Why this is safe:** `EventManagerController` has **zero class-level config** — every handler carries its own absolute `path`, `guards=[user_guard]`, and `dependencies`. Splitting cannot change routing. Only two external references exist: `controllers/__init__.py` and the frontend router list.

- [ ] **Step 1: Create `_common.py`**

Move: `SqidInt = Annotated[int, BeforeValidator(sink)]` (line 69) and `user_can_manage_submissions` (189-190). **Do not rename the `user`/`event` parameters** — `permission_check` (lib/guards.py:20-42) makes Litestar introspect the wrapped signature; those names are load-bearing DI.

- [ ] **Step 2: Create the 5 controller files** (bodies verbatim; per-file source lines)

| File | Class | Module-level items moved | Handlers (source lines) |
|---|---|---|---|
| `_schedule.py` | `ScheduleController` | `PutEventManageScheduleSession` (72-75), `PutEventManageScheduleForm` (78-80) | `get_event_manage_schedule` (263-321), `put_event_manage_schedule` (323-375), `get_event_manage_schedule_last_updated` (377-431) |
| `_submissions.py` | `SubmissionsController` | `get_event_games_dep` (131-182) — **stays a module-level DI provider**: its signature is introspected (injects `event`, `transaction`, query params `sort`/`desc`); it cannot become a service method | `get_event_manage_submissions` (433-500) |
| `_players.py` | `PlayersController` | `PutEventPlayerTransactionForm` (83-85), `add_transaction_with_delta` (196-258) | `get_event_manage_players` (502-547), `put_player_d20s` (549-575), `put_player_compensation` (577-603) |
| `_allocation.py` | `AllocationController` | `TierAsDict` (88-90), `AllocationPartyMetadata` (93-95), `PutEventManageAllocationSession` (98-100), `PutEventManageAllocationForm` (103-105) | `get_event_manage_allocation` (605-780), `post_event_do_allocation` (782-837), `post_event_unlock_allocation` (839-870), `post_event_lock_allocation` (872-903), `post_event_checkin_player` (905-945), `put_event_manage_allocation` (947-1011), `put_event_apply_compensation` (1013-1236) |
| `_settings.py` | `SettingsController` | `_empty_to_none` (108-113), `EmptyToNone` (116), `PutEventSettingsForm` (119-124) | `get_event_manage_settings` (1238-1257), `put_event_manage_settings` (1259-1293) |

Each class: `class XController(Controller):` with no class-level config in this task **except** where hoisting is trivially safe and identical across the file's handlers: `guards` and the `permission` dependency are identical on all 16 handlers and may be hoisted per-class; the `event` dependency may be hoisted in `_submissions.py`/`_players.py`/`_allocation.py`/`_settings.py` (each uses one `event_with(...)` option set per file) but NOT in `_schedule.py` (three different option sets — keep per-handler there). If in doubt, don't hoist — verbatim per-handler dicts are also acceptable for this task.

Imports per file: take the subsets identified in the analysis (e.g. `_allocation.py` is the sole user of `rich.pretty.pprint`, `bindparam`, `delete`, `postgresql.insert`, `aliased`, `user_id_ctx`, and the `services.algorithm.*` surface; `_players.py` the sole user of `catalog` and `lib.alerts`; `_settings.py` the sole user of `zoneinfo`). basedpyright + ruff F401 will catch over/under-imports — run them per file as you go.

- [ ] **Step 3: Update exports and router**

`controllers/__init__.py`: import + `__all__` for the 5 new controllers, drop `EventManagerController`. `apps/frontend/__init__.py`: replace `EventManagerController` import and `route_handlers` entry with the 5 classes (alphabetical placement). `git rm` `_event_manager.py`.

- [ ] **Step 4: Run checks** — baselines hold; route count still **84** (all paths absolute, nothing renamed).

- [ ] **Step 5: User smoke test** — every manage page loads: schedule (drag + save + last-updated-by), submissions (sort columns), players, allocation (both URL forms), settings.

- [ ] **Step 6: Commit** (confirm with user first): `git commit -m "Split event manager controller into five admin controllers"`

---

### Task 11: Admin ScheduleService (Phase 7, part 2)

**Files:**
- Create: `convergence_games/apps/frontend/admin/services/__init__.py`, `convergence_games/apps/frontend/admin/services/_schedule_service.py`
- Modify: `convergence_games/apps/frontend/admin/controllers/_schedule.py`

**Interfaces:**
- Consumes: `_schedule.py` from Task 10. `PutEventManageScheduleSession` moves from `_schedule.py` to `apps/frontend/admin/_common.py` (service needs it; importing from the controller would cycle).
- Produces: `ScheduleService` + `provide_schedule_service`; admin `services/` package for Tasks 12-13.

**Preserve verbatim:** `put_event_manage_schedule` deletes removed sessions **implicitly via `Event.sessions` delete-orphan cascade** (collection assignment at old line 370) — the service method must receive the `Event` instance with `sessions` loaded and assign the collection; passing `event_id` and bulk-deleting silently changes semantics (cascade also destroys `Session.allocations`). Keep the `print(data)` (340) in the controller and the count-mismatch `print` warning (301) in the service. Keep the committed-sessions-preserved-unless-committing logic exactly (344-368).

- [ ] **Step 1: Create `_schedule_service.py`** (line refs are original `_event_manager.py` lines)

```python
class ScheduleService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def unscheduled_games(self, event: Event) -> list[Game]:
        ...  # 287-301: times_to_run expansion, minus uncommitted existing sessions,
             # incl. the count-mismatch print warning

    def sessions_by_table_and_time_slot(self, event: Event) -> dict[tuple[int, int], list[Session]]:
        ...  # 309-319: cross-product dict comprehension, uncommitted only

    def replace_sessions(
        self, event: Event, session_specs: Sequence[PutEventManageScheduleSession], *, commit: bool
    ) -> None:
        ...  # 341-373 minus the print: seed committed sessions unless committing,
             # build uncommitted (+ committed duplicates when commit),
             # event.sessions = new_sessions; session.add(event). Sync — nothing awaits.

    def last_updated_summary(self, event: Event, current_user_id: int, last_saved: datetime | None) -> str:
        ...  # 393-426: max(updated_at) over uncommitted/committed, humanize deltas,
             # "you"/full-name/"never" strings, stale-data warning suffix


async def provide_schedule_service(transaction: AsyncSession) -> ScheduleService:
    return ScheduleService(transaction)
```

(First, second and fourth methods don't touch the session — kept on the class for one-import ergonomics.)

- [ ] **Step 2: Create `services/__init__.py`** exporting `ScheduleService`, `provide_schedule_service` with `__all__`; move `PutEventManageScheduleSession` to `_common.py` and update the controller import.

- [ ] **Step 3: Thin `_schedule.py`** — handlers keep deps/gates/renders; bodies become service calls. `get_event_manage_schedule` context uses `unscheduled_games` + `sessions_by_table_and_time_slot`; `put_event_manage_schedule` keeps `print(data)` then `schedule_service.replace_sessions(event, data.sessions, commit=data.commit)` (check the actual form field names when editing) + 204 response; `get_event_manage_schedule_last_updated` returns `Response(content=schedule_service.last_updated_summary(event, user.id, last_saved))`.

- [ ] **Step 4: Run checks** (baselines, 84 routes)

- [ ] **Step 5: User smoke test** — manage-schedule: drag games between tables/slots, save (uncommitted), commit, remove a session and save (verify it deletes), last-updated-by shows "you" + stale warning when another save happened.

- [ ] **Step 6: Commit** (confirm with user first): `git commit -m "Extract ScheduleService from schedule controller"`

---

### Task 12: Admin PlayerService (Phase 7, part 3)

**Files:**
- Create: `convergence_games/apps/frontend/admin/services/_player_service.py`
- Modify: `convergence_games/apps/frontend/admin/controllers/_players.py`, `convergence_games/apps/frontend/admin/services/__init__.py`

**Interfaces:**
- Consumes: admin `services/` package from Task 11.
- Produces: `PlayerService` + `provide_player_service`. `AllocationService` (Task 13) does not depend on it.

**Preserve verbatim:** the `with_loader_criteria` clauses on `list_players` (old 526-531) are **mandatory** — `User.latest_d20_transaction`/`latest_compensation_transaction` are viewonly correlated-subquery relationships (models `__mapper_args__`) that silently read cross-event balances without the criteria. The optimistic-concurrency `AlertError` ("You are out of sync with the database", old line 236) stays **in the service** so both call sites behave identically. `flush()` + `refresh()` (249-250) stay in the service (caller `swim`s the new row). The endpoint URL in the rendered component is built from the **raw** `event_sqid`/`user_sqid` path strings (256) — controller concern, keep there. The player list is global (all users), not event-scoped — keep.

- [ ] **Step 1: Create `_player_service.py`** (line refs = original `_event_manager.py`)

```python
class PlayerService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_players(self, event_id: int) -> Sequence[User]:
        ...  # 517-539: global User list ordered last_name/first_name, selectinloads +
             # the three event-scoped with_loader_criteria clauses

    async def add_balance_transaction[T: (UserEventD20Transaction, UserEventCompensationTransaction)](
        self,
        table_type: type[T],
        *,
        event_id: int,
        user_id: int,
        delta: int,
        expected_latest_transaction_id: int | None,
    ) -> T:
        ...  # 205-250: load player with event-filtered latest transaction,
             # out-of-sync AlertError, insert chained transaction row, flush + refresh.
             # Drop the dead Request param and Body annotation from the old helper (199, 203).
             # The table_type is UserEventD20Transaction branches (216-219, 228-231) stay.


async def provide_player_service(transaction: AsyncSession) -> PlayerService:
    return PlayerService(transaction)
```

(PEP 695 constrained TypeVar replaces the old untyped union — matches `.claude/rules/python-types.md`.)

- [ ] **Step 2: Update `services/__init__.py`** — add `PlayerService`, `provide_player_service`.

- [ ] **Step 3: Thin `_players.py`** — `get_event_manage_players` → `users = await player_service.list_players(event.id)` + render. `put_player_d20s`/`put_player_compensation` → decode sqids, call `add_balance_transaction` with the respective `table_type`, keep the `catalog.render("UserManageDelta", ...)`/`HTMXBlockTemplate` block (252-258) in a small controller-local helper shared by both handlers. Delete `add_transaction_with_delta`.

- [ ] **Step 4: Run checks** (baselines, 84 routes)

- [ ] **Step 5: User smoke test** — manage-players: balances show correct per-event values, add d20s, add compensation, out-of-sync error when submitting from a stale row (open two tabs).

- [ ] **Step 6: Commit** (confirm with user first): `git commit -m "Extract PlayerService from players controller"`

---

### Task 13: Admin AllocationService (Phase 7, part 4)

**Files:**
- Create: `convergence_games/apps/frontend/admin/services/_allocation_service.py`
- Modify: `convergence_games/apps/frontend/admin/controllers/_allocation.py`, `convergence_games/apps/frontend/admin/services/__init__.py`

**Interfaces:**
- Consumes: admin `services/` package.
- Produces: `AllocationService` + `provide_allocation_service`; `TierAsDict` + `AllocationPartyMetadata` move from `_allocation.py` into `_allocation_service.py` (service produces them; controller + `event_manage_allocation.html.jinja` consume — template references are by attribute, no template change).

**Preserve verbatim (highest-risk extraction in the plan):**
- `transaction.expunge_all()` (old line 1100) detaches the entire identity map. Therefore `apply_compensation` **takes `event_id: int`, not `Event`**, and the controller reads `event.id` before the call. It must remain the last DB work in the request.
- Keep the `cast(Select[tuple[...]], ...)` wrappers (669-699, 1043-1070) — basedpyright can't infer aliased column types.
- `resolve_time_slot` fallback `sorted_event_time_slots[-1]` (IndexError on zero slots) — keep.
- `put_event_manage_allocation` deletes **all** allocations for the slot including committed ones (unlike schedule PUT), with delete-after-build-before-add ordering — keep.
- `freeze_user_game_preferences` upsert has **no event/user scoping** (freezes globally) — keep.
- The `assert` at 1085 (no user in two parties), the `KeyError` risk at 1148 (GM without a leader row), and `insert().values([])` raising on empty played-games list (1209-1234) — all preserved, not fixed.
- Debug `print`/`pprint` (833-834, 1097) — carry into the service.
- `AlertError`? No — allocation raises `HTTPException(404)` (864, 897, 970): those move with the code into the service (litestar exception import in a service is acceptable here; it's the smallest-diff preservation).

- [ ] **Step 1: Create `_allocation_service.py`**

Move `TierAsDict`, `AllocationPartyMetadata` here. `PutEventManageAllocationSession` moves to `_common.py` (same cycle-avoidance as Task 11).

```python
class AllocationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _party_leader_subquery(time_slot_id: int) -> tuple[Subquery, AliasedClass[Party], AliasedClass[PartyUserLink]]:
        ...  # absorbs the duplicated block at 660-667 and 1035-1042 — this resolves the
             # in-source "# TODO: Extract common functionality" at 1034. Only sanctioned dedupe.

    def resolve_time_slot(self, event: Event, time_slot_sqid: Sqid | None) -> TimeSlot:
        ...  # 624-643: by-sqid with HTTPException(404), else next-upcoming with 60-min grace,
             # falling back to sorted_event_time_slots[-1]

    async def committed_sessions_for_slot(self, time_slot_id: int) -> Sequence[Session]:
        ...  # 645-655: joined to Table, ordered by Table.name

    async def allocation_groups(
        self, time_slot: TimeSlot, sessions: Sequence[Session]
    ) -> dict[int | None, list[tuple[User, Party | None, UserCheckinStatus | None, AllocationPartyMetadata]]]:
        ...  # 656-759: sessions_by_gm_id, the big cast(Select[...]) leaders query,
             # per-group has_d20/frozen-pref/played/over_18 computation, generate_tier_list,
             # TierAsDict via swim("Session", ...) + asdict, grouping, unallocated-bucket sort

    async def compensation_applied(self, event_id: int, time_slot_id: int) -> bool:
        ...  # 761-768: LIMIT 1 existence probe

    async def freeze_user_game_preferences(self, time_slot_id: int) -> None:
        ...  # 800-828: postgres INSERT..FROM SELECT..ON CONFLICT DO UPDATE, globally unscoped

    async def run_allocation(self, time_slot_id: int) -> None:
        ...  # 830-835: adapt_to_inputs, GameAllocator(max_iterations=5000, debug_print=False)
             # .allocate(sessions, parties, False), pprint dumps, adapt_results_to_database

    def set_time_slot_status(self, event: Event, time_slot_sqid: Sqid, status: TimeSlotStatus) -> TimeSlotStatus:
        ...  # 854-870 == 887-903 (lock/unlock are byte-identical modulo the enum):
             # find in event.time_slots, HTTPException(404), set status, session.add.
             # Returns the enum whose .value the handler renders.

    async def set_checkin(self, *, time_slot_id: int, user_id: int, checked_in: bool) -> None:
        ...  # 922-943: select-then-upsert UserCheckinStatus

    async def replace_allocations(
        self, time_slot: TimeSlot, allocation_specs: Sequence[PutEventManageAllocationSession], *, commit: bool
    ) -> None:
        ...  # 972-1009: build uncommitted rows (skip session-None overflow), committed
             # duplicates when commit, set time_slot.status, DELETE all slot allocations
             # (incl. committed), add_all — preserve ordering exactly

    async def apply_compensation(self, event_id: int, time_slot_id: int) -> None:
        ...  # 1029-1234 AS ONE METHOD, verbatim (only the two _party_leader_subquery call
             # sites change). Includes expunge_all at 1100. Do not decompose in this task —
             # a private-method breakdown is a candidate follow-up once smoke-tested.


async def provide_allocation_service(transaction: AsyncSession) -> AllocationService:
    return AllocationService(transaction)
```

(`Subquery` from `sqlalchemy.sql.selectable`, `AliasedClass` from `sqlalchemy.orm`.)

- [ ] **Step 2: Update `services/__init__.py`** — add `AllocationService`, `provide_allocation_service`, `AllocationPartyMetadata`, `TierAsDict`.

- [ ] **Step 3: Thin `_allocation.py`** — each of the 7 handlers keeps route/deps/gates, sqid parsing, `Redirect`/`Response`/template construction and the literal string returns (`"checked-in"`, `"Compensated"`, enum `.value`); bodies become service calls. `get_event_manage_allocation` = resolve_time_slot → committed_sessions_for_slot → allocation_groups → compensation_applied → render. `post_event_do_allocation` = freeze + run_allocation → Redirect. Lock/unlock both call `set_time_slot_status` with their enum. `put_event_apply_compensation` reads `event.id` into a local **before** calling `apply_compensation` (expunge safety), returns `"Compensated"`.

- [ ] **Step 4: Run checks** (baselines, 84 routes; `ruff check` — the C901 on the old handlers may shift location; no *new* rule violations)

- [ ] **Step 5: User smoke test (full allocation cycle on dev data)** — manage-allocation both URL forms; lock slot; run allocation; drag results; save (uncommitted); commit; unlock; check-in a player from the admin view; apply compensation and verify d20/compensation balances on manage-players; verify game detail/planner still see frozen preferences.

- [ ] **Step 6: Commit** (confirm with user first): `git commit -m "Extract AllocationService from allocation controller"`

---

### Task 14: Cleanup (Phase 8)

**Files:**
- Delete: `convergence_games/permissions/` (re-export shim; zero importers — verified by grep)
- Modify: `CLAUDE.md`, `.claude/rules/python-litestar.md`, `.claude/rules/python-models.md`, `.tasks/codebase-restructure/plan.md` (mark superseded/complete)

**Interfaces:** consumes the final structure from Tasks 1-13; produces nothing downstream.

- [ ] **Step 1: Delete the permissions shim**

```bash
grep -rn "convergence_games.permissions\|convergence_games import permissions" --include="*.py" convergence_games/ tests/ scripts/   # must be empty
git rm -r convergence_games/permissions
```

- [ ] **Step 2: Update `CLAUDE.md`** — Architecture section: replace the "Routing" description (`app/routers/` three-group text) with the `apps/` layout (`apps/frontend/<domain>/{controllers,services}/`, `apps/api/`, `apps/system/`, frontend router's profile-redirect hook); templates/static/frontend paths; `db/models/` package (one model per file, re-exported); note the service pattern (plain classes + `provide_*` factories). Update the Vite entry description (`convergence_games/frontend/index.ts` re-exporting co-located template TS).

- [ ] **Step 3: Update `.claude/rules/`** — `python-litestar.md:10` (controllers live in `apps/frontend/<domain>/controllers/`), `:30-31` (template paths), add a Services section (plain class + Provide factory pattern, services never commit); `python-models.md:5` ("All models in `convergence_games/db/models/`, one per file, re-exported from the package `__init__`").

- [ ] **Step 4: Residue sweep**

```bash
grep -rn "convergence_games\.app\b\|convergence_games/app\b" --include="*.py" --include="*.md" --include="*.json" --include="*.toml" --include="*.mts" --include="Dockerfile" . --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=ignore --exclude-dir=.tasks   # empty
```

- [ ] **Step 5: Full verification** — the four baseline checks; `npm run build`; `docker build .`; `litestar --app convergence_games.server.app:app database upgrade` against dev DB (no-op); user smoke-pass over the main flows.

- [ ] **Step 6: Mark `.tasks/codebase-restructure/plan.md`** frontmatter `status: superseded by design.md + implementation.md (complete)`.

- [ ] **Step 7: Commit** (confirm with user first): `git commit -m "Update docs and remove permissions shim after restructure"`
