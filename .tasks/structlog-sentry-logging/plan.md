---
title: Adopt structlog with Litestar and Sentry telemetry
created: 2026-05-07
status: draft
---

# Adopt structlog with Litestar and Sentry telemetry

## Context

The codebase has no formal logging. Diagnostics are done with `print()` (~30 calls in image loaders, the email sign-in listener, and the game allocator) and `rich.pretty.pprint()` (in `event_manager.py`, `query_adapter.py`, `game_allocator.py`). The style rule in `.claude/rules/python-style.md` explicitly notes that logging is "not yet formally set up" and lists loguru as a future option.

Sentry is initialised in `convergence_games/app/app_config/init_sentry.py` but receives no application logs as breadcrumbs or events — only unhandled exceptions and the Litestar integration's request traces. There is no per-request correlation ID, no structured user/event context on log records, and stdlib loggers from uvicorn/gunicorn/SQLAlchemy/asyncpg/httpx render with their default formatters into a separate stream from any future structured stream.

We want a single, structured log pipeline (structlog) wired into Litestar and stdlib logging, with output that is human-friendly in development and JSON in production, and with bound context (request_id, user_id, etc.) flowing through to Sentry as breadcrumbs, tags, and event context.

## Requirements

- structlog is the single logging entry point used by application code (`from convergence_games.logging import get_logger` or equivalent).
- All stdlib `logging` calls (uvicorn, gunicorn, SQLAlchemy, asyncpg, httpx, sentry-sdk, advanced-alchemy, alembic) are routed through the same structlog pipeline via `structlog.stdlib.ProcessorFormatter`.
- Output renderer is environment-aware: `structlog.dev.ConsoleRenderer` when `SETTINGS.ENVIRONMENT == "development"` (or `SETTINGS.DEBUG`), `structlog.processors.JSONRenderer()` otherwise.
- Per-request context is bound automatically via an ASGI middleware: `request_id` (uuid4), `method`, `path`, `user_id` (when the request has resolved a user). `X-Request-ID` is echoed in the response headers.
- Each request emits exactly one **canonical log line** at completion (`event="http_request"`) carrying status code, duration_ms, response size, route name, and every contextvar that was bound during the request. This is the single line a developer should be able to grep for to fully reconstruct what happened. (Pattern: <https://brandur.org/canonical-log-lines>; structlog endorsement: <https://www.structlog.org/en/stable/logging-best-practices.html>.)
- Sentry receives:
  - INFO+ logs as breadcrumbs and ERROR+ logs as issue events (via `sentry_sdk.integrations.logging.LoggingIntegration` defaults).
  - Per-request `request_id` set as a Sentry tag on the current scope; `user_id` set via `sentry_sdk.set_user`.
  - Bound structlog contextvars copied onto the Sentry scope as tags / contexts via a custom processor so issues created from log calls carry the same fields as the rendered log line.
- The game allocator's existing `debug_print` mechanism is replaced by `logger.debug(...)` calls (no `if debug_print:` guards — controlled by log level instead).
- `print()` and `rich.pretty.pprint()` are removed from non-CLI code paths and replaced with structured `logger.info` / `logger.debug` calls. Scripts under `scripts/` keep `print()` for human CLI output.
- Tests run quietly by default and ship a `caplog`-equivalent fixture (`structlog.testing.LogCapture`) for asserting on log records.
- `.claude/rules/python-style.md` "Logging" section is updated to point at the new convention.
- Type checking (`basedpyright`) and linting (`ruff check`, `ruff format --check`) pass.

## Technical Design

### Library selection

Add `structlog>=25.0` to `[project.dependencies]` in `pyproject.toml`. No other new dependencies — `sentry-sdk[litestar]>=2.26.1` already provides `LoggingIntegration`. Python version stays as-is (3.13 dev / 3.12 prod per `Dockerfile`); structlog supports both.

### Module layout

Add a `convergence_games/logging/` package that owns logging configuration. Keeping it out of `app/app_config/` means non-Litestar code paths (`scripts/`, `services/algorithm`, future workers) can call `configure_logging()` and `get_logger()` without importing app wiring.

```
convergence_games/
  logging/
    __init__.py          # re-exports configure_logging, get_logger
    config.py            # configure_logging() — structlog + stdlib bridge
    processors.py        # custom processors (sentry scope binding, drops, etc.)
    middleware.py        # LoggingContextMiddleware (ASGI) — binds request_id/method/path
```

Rationale for a dedicated package: `app/app_config/` is for Litestar plugin/config objects; `convergence_games/logging/` is shared infrastructure used by both the app and scripts.

### `convergence_games/logging/config.py` — structlog setup

A single `configure_logging()` function, idempotent (guard with a module-level flag), called from `app.py` before `init_sentry()` and from any script entry point.

Pipeline (mirroring the canonical structlog + stdlib recipe from <https://www.structlog.org/en/stable/standard-library.html>):

```python
shared_processors = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    structlog.processors.StackInfoRenderer(),
    structlog.dev.set_exc_info,
    sentry_scope_processor,  # see processors.py
]

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        *shared_processors,
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

renderer = (
    structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
    if SETTINGS.ENVIRONMENT == "development"
    else structlog.processors.JSONRenderer()
)

formatter = structlog.stdlib.ProcessorFormatter(
    foreign_pre_chain=shared_processors,
    processors=[
        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
        renderer,
    ],
)

handler = logging.StreamHandler()  # stderr by default
handler.setFormatter(formatter)
logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)

# Tame the noisy ones
logging.getLogger("sqlalchemy.engine").setLevel(
    logging.INFO if SETTINGS.DATABASE_ECHO else logging.WARNING
)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)  # superseded by canonical line
logging.getLogger("uvicorn.error").setLevel(logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("azure").setLevel(logging.WARNING)
```

`get_logger(name=None)` is a thin wrapper around `structlog.get_logger` that defaults to the caller's `__name__`-style usage idiom.

### `convergence_games/logging/processors.py` — Sentry handoff

`sentry_scope_processor(logger, method_name, event_dict)`:

1. Pull a fixed allow-list of bound keys (`request_id`, `user_id`, `event_id`, `game_id`, `session_id`, `path`, `method`) out of `event_dict`.
2. For each, call `sentry_sdk.set_tag(key, value)` on the current scope. This is cheap when there is no active Sentry hub.
3. Return `event_dict` unchanged so the values still render in console / JSON output.

This gives every Sentry event (issue or breadcrumb) the same context the log line has, without us having to remember at each call site.

### `convergence_games/logging/middleware.py` — request context + canonical log line

A small ASGI middleware (function-style, no Litestar `MiddlewareProtocol` required — but registered via Litestar's `middleware=` list). It only acts on `scope["type"] == "http"`:

1. Generate `request_id` (`uuid.uuid4().hex`) — unless an inbound `X-Request-ID` header is present, in which case reuse it (truncate to 64 chars to bound size).
2. `structlog.contextvars.clear_contextvars()` then `bind_contextvars(request_id=..., method=scope["method"], path=scope["path"])`.
3. Record `start = time.perf_counter()`.
4. `sentry_sdk.set_tag("request_id", request_id)` on the current Sentry scope.
5. Wrap `send` to:
   - Inject `x-request-id` into outbound response headers on `http.response.start`.
   - Capture `status` from `http.response.start` and accumulate `body_size` from `http.response.body` chunks.
6. After the inner `await app(scope, receive, send_wrapper)` returns, emit the canonical log line:
   ```python
   logger.info(
       "http_request",
       status=status,
       duration_ms=round((time.perf_counter() - start) * 1000, 2),
       response_bytes=body_size,
       route=scope.get("route_handler").name if scope.get("route_handler") else None,
   )
   ```
   structlog's `merge_contextvars` processor automatically folds in `request_id`, `method`, `path`, `user_id`, and any other fields that downstream code bound via `bind_contextvars` (or `structlog.contextvars.bound_contextvars(...)` context manager) — that's the canonical-log-line payoff: one searchable line per request with all the dimensions you'd want to slice on.
7. On exception, emit the same line with `status=500` and `exc_info=True` then re-raise.
8. Use a `try/finally` to call `clear_contextvars()` so bound state never leaks across requests in the same task / worker.

The middleware is added to Litestar via a new `LOGGING_MIDDLEWARE` constant exported alongside the existing plugins from `convergence_games/app/app_config/__init__.py`, then passed to `Litestar(middleware=[LOGGING_MIDDLEWARE], ...)` in `app/app.py`.

**Encouraged usage pattern in handlers/services:** instead of writing many small `logger.info(...)` calls, prefer `bind_contextvars(...)` (or the `bound_contextvars` context manager) so the canonical line at request end carries all the relevant fields. Reserve standalone log calls for noteworthy events (errors, side effects, integration callouts). This matches the structlog/Stripe canonical-log-line guidance.

A small helper — `convergence_games.logging.bind(**fields)` — re-exports `structlog.contextvars.bind_contextvars` so call sites import from one place. Also expose a `bound(**fields)` context manager wrapping `structlog.contextvars.bound_contextvars` for scoped fields.

### User binding

Once the JWT auth middleware has resolved the user, we bind `user_id` in a Litestar `before_request` hook. There is already a frontend `before_request` hook for the profile-completion redirect (referenced in CLAUDE.md). Add a top-level `before_request` on the Litestar app (in `app/app.py`) that:

```python
async def bind_logging_user(request: Request) -> None:
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "id", None) is not None:
        bind_contextvars(user_id=user.id)
        sentry_sdk.set_user({"id": user.id, "email": getattr(user, "email", None)})
```

This runs after auth, so `request.user` is populated for authenticated routes; for anon routes the call is a no-op.

### Litestar `logging_config` — what `StructLoggingConfig` actually does

Pass an explicit `logging_config=StructLoggingConfig(...)` to the Litestar app (reference: <https://docs.litestar.dev/2/usage/logging.html>). Concretely, `litestar.logging.config.StructLoggingConfig` does three things at app startup, on top of plain stdlib `LoggingConfig`:

1. **Calls `structlog.configure(...)`** with the processor list we pass it, the wrapper class, the logger factory, etc. This is the same `structlog.configure` call we'd otherwise make ourselves — so we avoid drift by sharing one canonical processor list (built in `convergence_games/logging/config.py`) between our own `configure_logging()` and Litestar's `StructLoggingConfig(processors=...)`.
2. **Configures stdlib `logging` via `dictConfig`** so non-structlog loggers (uvicorn, SQLAlchemy, sentry-sdk, etc.) hit the same handlers. We still install our `ProcessorFormatter` ourselves in `configure_logging()` because Litestar's default formatter set is more limited than the structlog/stdlib bridge we want.
3. **Adds `request.logger` per request** — a `BoundLogger` that handlers can grab as `request.logger.info(...)` to get a logger pre-bound with Litestar's request context (path params, request id if Litestar generates one, etc.). We do **not** depend on `request.logger` for our request-scoped fields — we use structlog's `contextvars` so any code that calls `get_logger()` inherits the same context without needing the `Request` object.

Mechanically: `configure_logging()` runs first (at module import in `app.py`) and sets up structlog + stdlib + Sentry handler chain. Then `StructLoggingConfig` is constructed sharing the same processor list, and Litestar invokes its own startup hook to (re)apply `structlog.configure` and `dictConfig`. `configure_logging()` is idempotent so this is safe — the second pass produces the same configuration. We could skip our own configure call and rely entirely on `StructLoggingConfig`, but doing it ourselves first means scripts and tests (which don't construct a Litestar app) get the same configuration via one call.

**Why we still emit our own canonical line instead of leaning on Litestar's request log:** `StructLoggingConfig` does not, in 2.16, emit a per-request "completed" log line with status + duration. It logs route handler exceptions (controlled by `log_exceptions` / `traceback_line_limit`), but normal requests are logged by uvicorn's `uvicorn.access` logger, which gives the bare `client - "GET /path" status` line and nothing else. Our middleware-emitted `http_request` line is what carries the contextvars (request_id, user_id, custom binds from inside the handler) and the duration.

### Avoiding duplicate per-request lines

There are three sources that could each produce a line per request:

1. **`uvicorn.access`** (stdlib logger) — bare `GET /path 200`. Useful at-a-glance, but redundant once we have a richer canonical line. **Decision: silence it** by setting `logging.getLogger("uvicorn.access").setLevel(logging.WARNING)` in `configure_logging()`. Our canonical line replaces it.
2. **Litestar's `StructLoggingConfig` exception logger** — only fires on exceptions. **Decision: keep** at INFO. The canonical line still fires (with `status=500` and `exc_info=True`), but Litestar's pre-traceback-truncation log is independently useful and emits with a different `event` string so it's not a duplicate.
3. **Our `LoggingContextMiddleware` canonical line** — the one we want. Always fires, success or error.

So "suppressing default behavior" means specifically: silence `uvicorn.access` to avoid two access-style lines per request. Nothing else gets suppressed.

### Sentry integration changes

`convergence_games/app/app_config/init_sentry.py`:

- Add `LoggingIntegration(level=logging.INFO, event_level=logging.ERROR)` to `integrations=[...]` (the defaults match these values, but listing it explicitly documents the choice).
- The existing `LitestarIntegration` is auto-enabled by `sentry-sdk[litestar]`; no change needed.
- `init_sentry()` is called *after* `configure_logging()` in `app.py` so the structlog + stdlib bridge is in place when Sentry attaches its handlers.

### Usage examples — handlers, services, repositories, listeners, scripts

The point of `merge_contextvars` is that **services and repositories never need to know whether they're running inside a request.** They call `get_logger()` and emit events; if a request middleware bound `request_id`/`user_id`/etc. earlier in the call stack, those fields automatically appear on the record. If they're called from a script, a test, or a background task, the fields are simply absent and the rest of the log line still works.

#### A handler

```python
# convergence_games/app/routers/frontend/event_manager.py
from convergence_games.logging import get_logger, bound

logger = get_logger(__name__)

class EventManagerController(Controller):
    @post("/events/{event_sqid:str}/games")
    async def create_game(
        self,
        event_sqid: str,
        data: PostGameForm,
        transaction: AsyncSession,
        user: User,
    ) -> Redirect:
        with bound(event_id=sink(event_sqid), action="create_game"):
            game = await game_service.create(transaction, data, user)
            logger.info("game_created", game_id=game.id)
            return Redirect(...)
```

The `with bound(event_id=..., action=...)` block scopes those fields to the duration of the block. Anything `game_service.create` logs internally inherits them. The canonical line at request end also inherits them.

#### A service

```python
# convergence_games/services/games.py
from convergence_games.logging import get_logger

logger = get_logger(__name__)

class GameService:
    async def create(self, session: AsyncSession, data: PostGameForm, user: User) -> Game:
        # No request awareness — but if called from a request handler, logs inherit
        # request_id, user_id, event_id, action via contextvars.
        logger.info("game_create_attempted", title=data.title)
        game = Game(...)
        session.add(game)
        await session.flush()
        logger.info("game_persisted", game_id=game.id)
        return game
```

Run from a request: log lines have `request_id`, `user_id`, `event_id`, `action`, `game_id`. Run from a script: log lines have just `title` and `game_id`. Same code; different surrounding context.

#### A repository / data access function

Same pattern — `logger = get_logger(__name__)` at module top, plain `logger.info("...", **fields)` at the call site. Don't pass `request` or `request.logger` through repository signatures; that couples the data layer to HTTP and breaks reuse from CLI / tests.

#### Event listener (`convergence_games/app/events.py`)

Litestar's `@listener` runs the handler in a worker task. asyncio's `Task` snapshots `contextvars` at creation time, so when Litestar dispatches `EVENT_EMAIL_SIGN_IN` from inside a request, the listener inherits `request_id`, `user_id`, etc. — verify this in Phase 2 with a test that emits an event from a request and asserts the listener log inherits the request_id. If for some reason it doesn't propagate, the dispatch site should explicitly pass relevant ids in the event payload and the listener should `bind(...)` them at the top.

```python
@listener(EVENT_EMAIL_SIGN_IN)
async def event_email_sign_in(email: str, ...) -> None:
    with bound(action="email_sign_in", email=email):
        logger.info("email_sign_in_code_generated")          # INFO — no code
        logger.debug("email_sign_in_code_value", code=code)   # DEBUG only — see Risks §1
        ...
        logger.info("email_sign_in_email_sent")
```

#### A script

```python
# scripts/create_mock_event.py
from convergence_games.logging import configure_logging, get_logger

configure_logging()
logger = get_logger("scripts.create_mock_event")

def main() -> None:
    logger.info("mock_event_creation_started")
    ...
    print("Created event 42")  # user-facing CLI output stays as print
```

`configure_logging()` is the only entry-point script needs. Diagnostics flow through structlog; user-facing output stays on `print()` so it isn't tagged with timestamps/levels.

#### A test

```python
# tests/services/test_game_service.py
from convergence_games.logging import bound

async def test_game_create_logs(log_output):
    async with session_factory() as session:
        with bound(test_id="t1"):
            await GameService().create(session, sample_form, sample_user)
    events = [e for e in log_output.entries if e["event"] == "game_persisted"]
    assert len(events) == 1
    assert events[0]["test_id"] == "t1"
```

The `log_output` fixture (defined in `tests/conftest.py`) gives a `LogCapture` so tests can assert on event names and fields without parsing strings.

### Replacing `print` and `pprint`

| File | Change |
| --- | --- |
| `convergence_games/app/events.py:38` | `logger.info("email_sign_in_code_generated", email=email, code=code)` (and consider gating `code` behind DEBUG to avoid logging the raw code in prod — see Risks §1). |
| `convergence_games/services/image/blob_image_loader.py:109` | `logger.info("image_saved", backend="blob", key=...)`. |
| `convergence_games/services/image/filesystem_image_loader.py:84,86,88,90` | `logger.info("image_saved", backend="filesystem", path=...)` (one event per branch, with descriptive event names). |
| `convergence_games/services/algorithm/game_allocator.py` (~20 prints) | Replace each `if debug_print: print(...)` with `logger.debug("alg_step", step=..., **fields)`. Drop the `debug_print` parameter from the public API where no callers pass it; if any do, keep it as a deprecated kwarg that just adjusts the logger level for a `with bound_contextvars(...):` block. |
| `convergence_games/services/algorithm/game_allocator.py:506,507,521,522,776,778` (`pprint`) | `logger.debug("alg_state", state=<dataclass.asdict or .__dict__>)` — let the JSON/console renderer format. |
| `convergence_games/services/algorithm/query_adapter.py:332,334` | `logger.debug("query_adapter_state", ...)`. |
| `convergence_games/app/routers/frontend/event_manager.py:833,834` | `logger.debug("event_manage_debug_dump", ...)`. |

`scripts/` keeps `print()` for user-facing output. Add `configure_logging()` to the top of any script that emits diagnostics through a logger.

### Tests

`tests/conftest.py` (create or extend):

```python
@pytest.fixture
def log_output() -> Iterator[structlog.testing.LogCapture]:
    cap = structlog.testing.LogCapture()
    structlog.configure(processors=[cap])
    try:
        yield cap
    finally:
        # Re-apply prod-ish config so other tests that don't request the fixture still work.
        from convergence_games.logging.config import configure_logging
        configure_logging()
```

Plus a session-scoped autouse fixture that calls `configure_logging()` once and sets the root level to WARNING so test runs are quiet.

### Style rule update

Update the "Logging" section in `.claude/rules/python-style.md` to reference structlog, the `get_logger` helper, the request-bound contextvars, and the convention of naming events with `snake_case` strings (event-style logging, not f-string messages).

## Implementation Plan

### Phase 1: Dependency and config skeleton

- [ ] **Add structlog dependency** (`pyproject.toml`)
  - Add `structlog>=25.0` to `[project.dependencies]`. Run `uv sync`.
- [ ] **Create logging package** (`convergence_games/logging/__init__.py`, `config.py`, `processors.py`, `middleware.py`)
  - `__init__.py` re-exports `configure_logging` and `get_logger`.
  - `config.py` implements `configure_logging()` per the design above with environment-aware renderer choice; idempotent guard.
  - `processors.py` implements `sentry_scope_processor`.
  - `middleware.py` implements `LoggingContextMiddleware` (ASGI scope/receive/send signature).

#### Phase 1 verification

- [ ] `uv sync` succeeds; `structlog` appears in `uv.lock`.
- [ ] `python -c "from convergence_games.logging import configure_logging, get_logger; configure_logging(); get_logger().info('boot_test', ok=True)"` prints a structured line.
- [ ] `basedpyright` — no new errors.
- [ ] `ruff check` and `ruff format --check` — clean.

### Phase 2: Wire into Litestar and Sentry

- [ ] **Configure Litestar `logging_config`** (`convergence_games/app/app.py`)
  - Build a `StructLoggingConfig` from `litestar.logging.config` using the shared processor list from `convergence_games.logging.config`.
  - Call `configure_logging()` at module import (top of `app.py`) before `init_sentry()`.
  - Pass `logging_config=...` to `Litestar(...)`.
- [ ] **Add Sentry LoggingIntegration** (`convergence_games/app/app_config/init_sentry.py`)
  - Import and add `LoggingIntegration(level=logging.INFO, event_level=logging.ERROR)` to `integrations=[...]`.
- [ ] **Register middleware and before_request hook** (`convergence_games/app/app.py`)
  - Import `LoggingContextMiddleware` from `convergence_games.logging.middleware`.
  - Add `middleware=[LoggingContextMiddleware]` to `Litestar(...)`.
  - Add a top-level `before_request=bind_logging_user` hook (defined locally in `app.py` or in `convergence_games/logging/middleware.py`).
- [ ] **Canonical log line emission**
  - In `LoggingContextMiddleware`, capture status / duration / body size and emit a single `logger.info("http_request", ...)` per request as described in the design.
  - Silence `uvicorn.access` (set level to WARNING) so the canonical line is the only per-request access record; keep `uvicorn.error` and Litestar's exception logger at INFO.

#### Phase 2 verification

- [ ] `litestar --app convergence_games.app:app run` starts without errors.
- [ ] `curl -i http://localhost:8000/` returns an `X-Request-ID` header.
- [ ] Server stderr shows uvicorn access logs in structlog format (pretty in dev).
- [ ] Each request produces exactly one `http_request` canonical log line with `status`, `duration_ms`, `request_id`, `method`, `path`, and (when authenticated) `user_id`.
- [ ] `basedpyright`, `ruff check` clean.

### Phase 3: Replace `print` calls in app code

- [ ] **Image loaders** (`convergence_games/services/image/blob_image_loader.py:109`, `filesystem_image_loader.py:84,86,88,90`)
  - Replace each `print(...)` with `logger.info("image_<verb>", **fields)`.
- [ ] **Event listener** (`convergence_games/app/events.py:38`)
  - Replace `print(...)` with `logger.info("email_sign_in_code_generated", email=email)` — do NOT log `code` at INFO; log it at DEBUG only (see Risks §1).
- [ ] **Game allocator prints** (`convergence_games/services/algorithm/game_allocator.py` — all `print(...)` lines)
  - Convert every `print(...)` (including those inside `if debug_print:` blocks) to `logger.debug("alg_<step>", **fields)`.
  - Remove the `debug_print` parameter from `GameAllocator` / public functions; verbosity is now controlled by log level. Update any callers (search for `debug_print=` usage; expect <5 sites).

#### Phase 3 verification

- [ ] `rg -n "print\(" convergence_games/` returns only intentional cases (none expected outside `scripts/`).
- [ ] Allocator unit tests still pass: `pytest tests/services/algorithm/`.
- [ ] `basedpyright`, `ruff check` clean.

### Phase 4: Replace `rich.pretty.pprint` debug dumps

- [ ] **Algorithm pprints** (`convergence_games/services/algorithm/game_allocator.py:506,507,521,522,776,778`, `query_adapter.py:332,334`)
  - Replace with `logger.debug("alg_state", **{"<descriptive>": <value>})`. The value will be rendered by the renderer (ConsoleRenderer pretty-prints in dev; JSONRenderer falls back via `default=repr`).
  - Drop the `from rich.pretty import pprint` import where it's now unused.
- [ ] **Event manager debug dump** (`convergence_games/app/routers/frontend/event_manager.py:833,834`)
  - Replace with `logger.debug("event_manage_debug_dump", ...)`.

#### Phase 4 verification

- [ ] `rg -n "pprint" convergence_games/` returns only places that legitimately need rich (none expected).
- [ ] Manually hit an event-manage page in dev with `LOG_LEVEL=DEBUG` and confirm the structured dump appears.
- [ ] `basedpyright`, `ruff check` clean.

### Phase 5: Tests and rules

- [ ] **Pytest fixtures** (`tests/conftest.py`)
  - Add session-scoped autouse fixture calling `configure_logging()`; set root level to WARNING during tests.
  - Add `log_output` fixture using `structlog.testing.LogCapture` for opt-in assertions.
- [ ] **Smoke test** (`tests/logging/test_logging_config.py` — new file)
  - Test that `configure_logging()` is idempotent.
  - Test that `bind_contextvars(request_id="abc")` then `logger.info("x")` puts `request_id="abc"` in the captured event dict.
  - Test that `sentry_scope_processor` does not raise when sentry is disabled.
- [ ] **Canonical line + leak test** (`tests/logging/test_middleware.py` — new file)
  - Drive `LoggingContextMiddleware` with a stub ASGI app twice in sequence; assert exactly one `http_request` event per request, with the expected `status`, `duration_ms`, `request_id`, `method`, `path` fields.
  - Bind extra fields via `bound_contextvars(custom="x")` inside the stub handler and assert the canonical line includes `custom="x"`.
  - Assert that after both requests, `structlog.contextvars.get_contextvars()` is empty (no leak).
- [ ] **Update style rule** (`.claude/rules/python-style.md`)
  - Replace the "Logging" section: declare structlog as the standard, document `get_logger`, contextvars, event-name convention, dev-vs-prod renderer behaviour, link to `convergence_games/logging/`.

#### Phase 5 verification

- [ ] `pytest` — all tests pass; output is quiet (no stray INFO lines unless a test fails).
- [ ] `pytest tests/logging/ -v` — new tests pass.
- [ ] `basedpyright`, `ruff check`, `ruff format --check` clean.

### Phase 6: Manual end-to-end check

- [ ] Run `litestar --app convergence_games.app:app run --reload` locally.
- [ ] Hit a few routes (anonymous + logged in); confirm logs include `request_id`, `method`, `path`, and `user_id` for authenticated requests.
- [ ] Trigger an exception path (e.g. a forced 500); confirm Sentry receives the event with `request_id` tag and breadcrumbs from preceding INFO logs.
- [ ] Toggle `ENVIRONMENT=production` locally; confirm output flips to JSON.
- [ ] Run the game allocator script with default level (silent) and with `LOG_LEVEL=DEBUG` (verbose); confirm parity with the previous `debug_print=True` output.

## Acceptance Criteria

- [ ] `basedpyright` passes with no new errors.
- [ ] `ruff check` and `ruff format --check` pass.
- [ ] `pytest` passes; test output is quiet at default level.
- [ ] `rg -n "print\(" convergence_games/` returns no diagnostic prints (only intentional CLI/user output, which lives in `scripts/`).
- [ ] `rg -n "rich.pretty" convergence_games/` returns nothing (or only template / non-logging uses).
- [ ] Dev server boots, requests carry an `X-Request-ID` header, and stderr is pretty-rendered structlog output.
- [ ] Setting `ENVIRONMENT=production` flips output to JSON without code changes.
- [ ] An induced exception in a route appears in Sentry with `request_id` and `user_id` (when applicable) on the event scope, with INFO-level structlog calls from the same request showing up as breadcrumbs.

## Risks and Mitigations

1. **Logging the email sign-in code in production logs is a security regression.** The existing `print()` exposes the 6-digit code; lifting it to `logger.info(...)` would put it into Sentry breadcrumbs and any prod log aggregator. Mitigation: log the code only at DEBUG level (default off in prod), or omit it entirely from the log record and rely on email delivery + DB record to debug.
2. **Sentry event flooding from ERROR-level logs.** `LoggingIntegration` defaults to creating an issue per `logger.error`. If existing libraries emit ERROR for benign cases (e.g. asyncpg disconnects on shutdown), this could spam Sentry. Mitigation: monitor after rollout; set `event_level=logging.CRITICAL` if needed, or add a `before_send` filter listing known-noisy `logger.name`s.
3. **Forgetting `clear_contextvars()` leaks user context across requests** — particularly with `gunicorn -k uvicorn.workers.UvicornWorker` where workers reuse async tasks. Mitigation: middleware uses `try/finally` to clear, plus a smoke test in `tests/logging/` that fires two sequential mock requests and asserts no leak.
7. **Event listeners may not inherit request contextvars.** Litestar dispatches `@listener` handlers via a worker pool; if they're scheduled in a way that doesn't snapshot contextvars at dispatch time, listener logs will be missing `request_id` / `user_id`. Mitigation: add an explicit test in Phase 2 that emits an event from inside a request and asserts the listener log inherits `request_id`. If it doesn't, the `emit` call site passes ids in the event payload and the listener binds them at the top of its body.
8. **`configure_logging()` runs twice — once from us, once from `StructLoggingConfig`.** Litestar invokes `structlog.configure(...)` from its app-init hook. Mitigation: same processor list shared between both call sites; `configure_logging()` is idempotent; verify in Phase 2 that no warnings are emitted and the second pass produces the same effective config.
4. **`StructLoggingConfig` from Litestar may not be available or stable across `litestar>=2.16`.** Mitigation: pin to the import path that exists in the installed version (`litestar.logging.config.StructLoggingConfig`); fall back to a hand-built `LoggingConfig` if necessary. Verify in Phase 2 before wiring widely.
5. **`debug_print=` parameter removal on the allocator is a public-API change.** It's an internal service, but external callers may exist (scripts, tests). Mitigation: grep for `debug_print=` before deletion, leave the kwarg in place but ignored if any usage remains, with a warning log on first use.
6. **Idempotency of `configure_logging()` matters under reload / multi-worker.** Mitigation: module-level `_configured` flag; `logging.basicConfig(..., force=True)` so re-applying overwrites previous handlers cleanly.

## Notes

- Reference reading consulted while planning:
  - <https://docs.litestar.dev/2/usage/logging.html> — the `StructLoggingConfig` and `LoggingConfig` classes Litestar exposes.
  - <https://github.com/hynek/structlog> — canonical structlog docs, particularly the "Standard Library" recipe for the `ProcessorFormatter` bridge.
  - <https://www.structlog.org/en/stable/logging-best-practices.html> — structlog's logging best-practices guide; endorses the canonical-log-line pattern and `bind_contextvars` for request-scoped fields.
  - <https://brandur.org/canonical-log-lines> — Stripe's canonical-log-line writeup; the underlying motivation for emitting one fat structured line per request rather than many small ones.
  - sentry-sdk [`LoggingIntegration` docs](https://docs.sentry.io/platforms/python/integrations/logging/) — defaults and `event_level` / `level` knobs.
- "Sentry Logs" (the experimental `_experiments={"enable_logs": True}`) is intentionally out of scope for this task — we can layer it on later once the structlog pipeline is stable.
- The `sentry_sdk.integrations.litestar.LitestarIntegration` already opens a Sentry scope per request; our middleware additions piggy-back on that scope rather than creating a new one.
- Future follow-ups (not in this task): (a) audit log fields for PII before enabling JSON in prod with a real log aggregator, (b) add structured access logs with response status / duration, (c) consider `enable_logs=True` once GA in sentry-sdk.
