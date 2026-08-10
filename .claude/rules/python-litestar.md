---
alwaysApply: false
paths: **/*.py
---

# Litestar Framework Conventions

## Route Handlers

- Organize routes in `Controller` classes, one per file in `convergence_games/apps/frontend/<domain>/controllers/` (domains: `accounts`, `admin`, `debug`, `games`, `player`, `public`, `redirects`, `user`).
- Use `@get`, `@post`, `@put`, `@delete` decorators from litestar.
- All handlers are `async def`.
- Apply `guards=[user_guard]` on endpoints requiring authentication.
- Return `Template` or `HTMXBlockTemplate` for HTML responses, `Response` or `Redirect` for others.

## Dependency Injection

- Dependencies declared in `convergence_games/lib/deps.py` (registered app-wide via `server/core.py`).
- Inject via handler parameter names: `transaction: AsyncSession`, `user: User`, `image_loader: ImageLoader`.
- `transaction` provides an auto-committing async session wrapped in `begin()`.

## Request Parameters

- Use `Annotated[T, Body(media_type=RequestEncodingType.URL_ENCODED)]` for form data.
- Use `Annotated[T, Parameter()]` for query parameters.
- Define request schemas as Pydantic `BaseModel` subclasses.

## Templates (JinjaX)

- Pages in `convergence_games/templates/pages/` (lowercase `.html.jinja`).
- Reusable components in `convergence_games/templates/components/` (PascalCase `.html.jinja`).
- All JinjaX components automatically receive `request` via custom passthrough in template_config.
- Custom Jinja filters/globals registered in `convergence_games/lib/template.py`.

## Error Handling

- `UserNotLoggedInError` for auth failures (redirects to login).
- `AlertError` for user-facing error messages with toast alerts.
- `IntegrityError` caught in transaction provider, raised as 409 Conflict.
- Custom exception handlers registered in `convergence_games/server/core.py`.

## Events

- Litestar event listeners via `@listener("event_name")` for decoupled side effects (e.g., sending emails).

## Services

- Business logic lives in `apps/frontend/<domain>/services/`, one service class per module (e.g., `_game_service.py` -> `GameService`).
- A service is a plain class holding an injected session: `def __init__(self, session: AsyncSession) -> None: self._session = session`.
- Each service module defines a `provide_<name>_service(transaction: AsyncSession) -> XService` factory next to the class.
- Controllers wire the factory in via `dependencies = {"x_service": Provide(provide_x_service)}`.
- Services never call `.commit()` — the `transaction` dependency's `begin()` wrapper commits at the request boundary.
- Form models/helpers shared across a domain's controllers live in a domain-local `_forms.py` / `_common.py` file (e.g., `apps/frontend/games/_forms.py`, `apps/frontend/admin/_common.py`), not duplicated per controller.

## Permissions

- `user_has_permission()` from `convergence_games/lib/permissions.py` checks role-based access.
- Available as both a route guard helper and a Jinja template filter.
- Role hierarchy: Owner > Manager > Reader > Player.
