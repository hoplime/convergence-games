# Litestar Framework Conventions

## Route Handlers

- Organize routes in `Controller` classes, one per file in `convergence_games/app/routers/frontend/`.
- Use `@get`, `@post`, `@put`, `@delete` decorators from litestar.
- All handlers are `async def`.
- Apply `guards=[user_guard]` on endpoints requiring authentication.
- Return `Template` or `HTMXBlockTemplate` for HTML responses, `Response` or `Redirect` for others.

## Dependency Injection

- Dependencies declared in `convergence_games/app/app_config/dependencies.py`.
- Inject via handler parameter names: `transaction: AsyncSession`, `user: User`, `image_loader: ImageLoader`.
- `transaction` provides an auto-committing async session wrapped in `begin()`.

## Request Parameters

- Use `Annotated[T, Body(media_type=RequestEncodingType.URL_ENCODED)]` for form data.
- Use `Annotated[T, Parameter()]` for query parameters.
- Define request schemas as Pydantic `BaseModel` subclasses.

## Templates (JinjaX)

- Pages in `convergence_games/app/templates/pages/` (lowercase `.html.jinja`).
- Reusable components in `convergence_games/app/templates/components/` (PascalCase `.html.jinja`).
- All JinjaX components automatically receive `request` via custom passthrough in template_config.
- Custom Jinja filters/globals registered in `convergence_games/app/app_config/template_config.py`.

## Error Handling

- `UserNotLoggedInError` for auth failures (redirects to login).
- `AlertError` for user-facing error messages with toast alerts.
- `IntegrityError` caught in transaction provider, raised as 409 Conflict.
- Custom exception handlers registered in `app_config/exception_handlers.py`.

## Events

- Litestar event listeners via `@listener("event_name")` for decoupled side effects (e.g., sending emails).

## Permissions

- `user_has_permission()` from `convergence_games/permissions/` checks role-based access.
- Available as both a route guard helper and a Jinja template filter.
- Role hierarchy: Owner > Manager > Reader > Player.
