---
title: Codebase restructure — remaining work (design)
created: 2026-08-10
status: approved
supersedes: plan.md (phases 1-2 and controller moves of phase 3 complete as of ecc594d)
---

# Codebase Restructure — Remaining Work

## Overview

Finish the restructure of Convergence Games (Litestar SSR app) into a domain-grouped layout. Phases 1-2 of the original plan plus the controller moves of Phase 3 are complete on `feature/restructure` (through commit `ecc594d`). During execution the structure diverged from the original plan doc: `domain/` was renamed to `apps/frontend/<domain>/`, with `apps/api/` (debug JSON API) and `apps/system/` (health, static, favicon) as sibling apps.

Remaining work: finish asset moves out of `app/` (templates, static, TypeScript), split the monolithic `db/models.py` into one model per file, extract service classes for the games/player/admin domains, and clean up docs and shims.

## Current State (done — context only)

- `lib/` holds shared utilities: alerts, auth (JWT cookie), context, deps, events, exceptions, guards, ocean (sqids), permissions, request/response types, sentry, template (JinjaX catalog).
- `server/` holds `app.py` (`create_app()` factory), `config.py`, `core.py` (`ApplicationCore` init plugin registering routers/deps/handlers), `plugins.py`.
- Controllers live in `apps/frontend/<domain>/controllers/` with `_underscore.py` naming and `__all__` exports:
  - `accounts/` — `_auth_pages.py`, `_email_auth.py`, `_oauth.py`
  - `admin/` — `_event_manager.py` (1293-line monolith, split pending)
  - `debug/` — `_debug.py`
  - `games/` — `_browse.py`, `_components.py`, `_detail.py`, `_search.py`, `_submit.py`
  - `player/` — `_party.py`, `_planner.py`, `_preferences.py`
  - `public/` — `_public.py`
  - `redirects/` — `_redirects.py`
  - `user/` — `_profile.py`, `_settings.py`, `_submissions.py`
- `apps/api/_debug.py`, `apps/system/{_favicon,_health,_static}.py`.
- The frontend router (`apps/frontend/__init__.py`) carries the profile-setup `before_request` redirect hook.
- Migrations live in `db/migrations/`; entrypoint is `convergence_games.server.app:app`.
- Still in old `app/`: `templates/`, `static/`, `lib/` (TS source: `index.ts`, `editor.ts`). `app/app_config/`, `app/common/`, `app/routers/` are empty husks (pycache only).
- `permissions/__init__.py` remains as a re-export shim to `lib/permissions`.

## Requirements

- All existing functionality preserved — no route changes, no logic changes, no schema changes.
- Assets move to package top-level: `convergence_games/templates/`, `convergence_games/static/`, `convergence_games/frontend/` (TS source). `app/` deleted.
- One model per file under `db/models/` with `_underscore` naming; `from convergence_games.db.models import X` keeps working for all 30 models.
- Thin controllers delegating to service classes in `apps/frontend/<domain>/services/` for games, player, admin domains.
- Auth controllers (`_oauth.py`, `_email_auth.py`, `_auth_pages.py`) stay as-is — inherently HTTP-coupled.
- `services/algorithm/` and `services/image/` stay at top level — cross-cutting.
- Docs (`CLAUDE.md`, `.claude/rules/*.md`) updated to match final structure.
- Each phase independently verifiable; app must work after every phase.

## Design

### Phase 3b — finish asset moves

Move `app/templates/` → `templates/`, `app/static/` → `static/`, `app/lib/*.ts` → `frontend/`. All Python asset paths flow through `paths.py` (consumed by `lib/template.py`, `apps/system/_static.py`, `apps/system/_favicon.py`, `services/image/image_loader_from_settings.py`), so the Python-side change is editing `paths.py` only (drop `APP_DIR_PATH`). Non-Python updates: `vite.config.mts` (entry `convergence_games/app/lib` → `convergence_games/frontend`, outDir → `convergence_games/static/js`), `package.json` tailwind output paths, Dockerfile COPY/mv paths, any tsconfig include paths. Note: `static/images/uploads/` contains dev filesystem-mode image uploads and moves with the directory. Delete `app/` entirely (including empty husks).

### Phase 4 — model split

Create `db/models/` package replacing `db/models.py` (1013 lines, 30 classes):

- `_base.py` — `Base`, `UserAuditColumns`, `foreign_key_constraint_with_event()`.
- One `_<model>.py` per model class; `@sqla_event.listens_for` handlers stay in the same file as their model (GameRequirement, GameRequirementTimeSlotLink, Table).
- `__init__.py` imports every module (so all mappers register before configuration) and re-exports via `__all__` — zero downstream import changes.
- All relationships already use string targets, so cross-file references resolve at mapper-configuration time.

Verify: `litestar database make-migrations` produces no new migration (schema identical).

### Phases 5-7 — service extraction

Service pattern (no base class, no repository abstraction):

```python
class PartyService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
```

DI: `provide_<x>_service(transaction: AsyncSession)` factories registered per-controller via `dependencies = {"party_service": Provide(...)}`. Controllers keep: Pydantic form models, validation error handlers, template rendering (HTMX block names, `catalog.render()`). Services own: queries, link-diffing, orchestration, persistence.

- **Phase 5, games**: `apps/frontend/games/services/` — `_game_service.py` (create/update game, link-diffing ~150 lines from `_submit.py`, submission status, detail queries, helpers `create_if_not_exists`/`create_new_links`/`create_image_links`/`create_image`), `_search_service.py` (fuzzy search + autocomplete).
- **Phase 6, player**: `apps/frontend/player/services/` — `_party_service.py` (create/join/leave/promote/remove/check-in/out, GM checks, party+session queries), `_planner_service.py` (planner data: party/preference/tier computation), `_preference_service.py` (set preference, mark played, get preferences).
- **Phase 7, admin**: split `_event_manager.py` into 5 controllers (`_schedule.py`, `_submissions.py`, `_players.py`, `_allocation.py`, `_settings.py` — one per `/event/{sqid}/manage-*` route group) plus `apps/frontend/admin/services/` — `_schedule_service.py`, `_allocation_service.py` (run/save/commit allocation, lock/unlock, compensation ~140 lines), `_player_service.py` (player queries, D20/compensation transactions). Extract with zero semantic changes — this file has the codebase's most complex queries (`aliased()`, `with_loader_criteria()`, `expunge_all()`).

Phases 5-7 are mutually independent; sequential recommended to refine the pattern.

### Phase 8 — cleanup

Delete `permissions/` shim (update its importers to `lib/permissions`). Update `CLAUDE.md` architecture section and `.claude/rules/python-litestar.md` / `python-models.md` (still reference `app/routers/frontend/`, `db/models.py`, `db/ocean.py`, `permissions/`). Verify Dockerfile builds. Confirm no `convergence_games.app` references remain.

## Verification (every phase)

- `basedpyright` — no new errors (baseline ~30)
- `ruff check` — no new errors (baseline 36: C901, N806, migration lint)
- `PYTHONPATH=. pytest tests/` — 28 pass
- App instantiates with 84 routes
- User smoke-tests via VSCode debugger (never launch litestar directly)

Phase-specific: Phase 3b — CSS/JS load, templates render, favicons serve, `npm run build` works, Dockerfile builds. Phase 4 — no-op migration check. Phases 5-7 — manual flow checks per domain (submit/edit game, search; party lifecycle, planner tiers, preferences; schedule/submissions/players/allocation/settings manage pages).

## Out of Scope

- Route/URL changes (deferred renames listed in plan.md Notes: `/editor-test`, `/components/image-upload`, `/search/*`).
- Repository/DTO abstractions, msgspec, CompositeServiceMixin (rejected in original planning).
- Algorithm service restructure.
- Fixing baseline type/lint errors.
