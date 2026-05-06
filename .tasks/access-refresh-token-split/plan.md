---
title: Split single auth token into access + refresh with server-side sessions
created: 2026-05-06
status: draft
---

# Split single auth token into access + refresh with server-side sessions

## Context

Authentication today uses a single JWT cookie (`token`) issued by `JWTCookieAuth` in `convergence_games/app/app_config/jwt_cookie_auth.py:63`, with a 365-day TTL. Every permission claim — `first_name`, `last_name`, `over_18`, `event_roles` — is baked into the token's `extras` and reconstructed into a `User` object by `retrieve_user_handler` (`jwt_cookie_auth.py:38`) without touching the DB. A user can only pick up a permission change (e.g. an admin granting them an event role) by signing out and back in. There is also no server-side concept of a session: the cookie cannot be revoked without rotating `TOKEN_SECRET`, and we have no record of when a user was last active or what devices are signed in.

The intended outcome:

- Two cookies, conventional access/refresh split. The short-lived **access** cookie carries the same claims used today (so the request hot path stays a no-DB-hit JWT decode). The long-lived **refresh** cookie identifies a server-side `user_session` row and is the only thing that can mint new access tokens.
- A permission change becomes visible without re-login: the next time the access token expires (worst case = access TTL = 15 min), the middleware silently mints a new one with fresh claims pulled from the DB.
- A new `user_session` table provides last-activity tracking, server-side revocation, and per-device sessions UI on `/profile`.
- Refresh-token rotation with reuse detection: every refresh issues a new `jti` and revokes the previous one; replaying a revoked `jti` revokes the entire session family.
- All previously-issued legacy `token` cookies keep working — the middleware decodes them as before, and on first activity transparently upgrades the browser to the new access + refresh pair (no forced logouts at deploy time).

## Requirements

- Two HttpOnly cookies after the rollout: `access` (15 min TTL) and `refresh` (180 day TTL). Both `Secure` in production (controlled by the same logic as today's single cookie).
- A new `user_session` SQLAlchemy model and Alembic migration capturing: `user_id`, `jti`, `family_id`, `created_at`, `last_used_at`, `expires_at`, `revoked_at`, `revoked_reason`, `user_agent`. (No IP — privacy minimisation; browser/OS parsed from UA is enough for the UI.)
- The hot request path (access cookie present + valid) does not hit the DB for authentication — the access JWT carries the same claims `build_token_extras` packs today.
- When the access cookie is missing or expired but a valid refresh cookie is present, the middleware: (a) loads the user + event_roles from the DB, (b) updates `last_used_at` on the session row, (c) rotates the refresh `jti` (issuing a new refresh cookie and marking the previous `jti` as `rotated`), (d) issues a new access cookie, (e) authenticates the request as the user. All of this happens inside one ASGI request.
- Refresh-token reuse detection: presenting a `jti` whose row is in state `rotated` or `revoked` revokes every row in the same `family_id` and clears the user's auth cookies. The request is treated as unauthenticated.
- Backwards compatibility: a request that arrives with **only** the legacy `token` cookie (no `access`/`refresh`) is authenticated using the legacy decode path, and the response upgrades the browser to access + refresh + a `user_session` row, while clearing the legacy `token` cookie.
- Logout from the navbar revokes only the current session row (`revoked_reason='logout'`) and clears all three cookies (`access`, `refresh`, legacy `token`).
- Sessions panel on `/profile` lists the user's active sessions with: parsed User-Agent (browser + OS), created at, last seen at, "this device" indicator, and a per-row revoke button. A "Sign out everywhere" button revokes all of the user's sessions in one shot.
- New endpoints: `POST /auth/sessions/{session_sqid}/revoke` (per-session) and `POST /auth/logout-everywhere`.
- Permission changes propagate within the access TTL window (15 min worst case) without explicit user action. No `roles_invalidated_at` shortcut is added in this task; the 15 min delay is acceptable.
- All existing call sites of `jwt_cookie_auth.login(...)` (`convergence_games/app/common/auth.py:195`, `convergence_games/app/routers/frontend/profile.py:264`) are replaced with the new issuer helper that creates a `user_session` row and emits both new cookies.
- Existing route guards (`user_guard`, `connection.user`) keep working unchanged. The change is transparent to all controllers.
- The `LaxJWTCookieAuthenticationMiddleware` behaviour is preserved: invalid or missing tokens leave `connection.user = None` rather than raising.
- Tests: middleware unit tests cover the access-valid, refresh-valid, refresh-rotated-reuse, refresh-expired, legacy-only, and no-cookie paths. New `tests/db/test_user_session.py` covers the rotation and revocation helpers.

## Technical Design

### Data model

New model in `convergence_games/db/models.py`, following the same `Base` (`BigIntAuditBase` + `UserAuditColumns`) pattern as the rest of the table family:

```python
class UserSession(Base):
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)
    jti: Mapped[str] = mapped_column(unique=True, index=True)
    family_id: Mapped[str] = mapped_column(index=True)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTimeUTC(timezone=True))
    last_used_at: Mapped[dt.datetime] = mapped_column(DateTimeUTC(timezone=True))
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTimeUTC(timezone=True), nullable=True, default=None)
    revoked_reason: Mapped[str | None] = mapped_column(nullable=True, default=None)  # 'logout' | 'rotated' | 'reuse_detected' | 'admin' | 'logout_everywhere'
    user_agent: Mapped[str | None] = mapped_column(nullable=True, default=None)

    user: Mapped[User] = relationship(foreign_keys=user_id, lazy="noload")
```

`jti` is a fresh `uuid.uuid4().hex` per row. `family_id` is set to the original `jti` on session creation and copied across all rotations of that session (so reuse detection can `UPDATE user_session SET revoked_at=now(), revoked_reason='reuse_detected' WHERE family_id = :fid`).

`User.sessions` back-reference is **not** added — it would tempt N+1 access. Sessions are loaded explicitly via `select(UserSession).where(UserSession.user_id == ...)` in the helper.

Alembic migration uses `litestar --app convergence_games.app:app database make-migrations -m "add user_session table"`. The auto-generated migration adds `user_session` with the same `BigIntAuditBase` + audit columns as every other table.

A `UserSession` sqid salt is registered automatically by the existing `_ink()` machinery in `convergence_games/db/ocean.py` — the new endpoints use `swim`/`sink` for URL parameters (matches the rest of the codebase per `python-models.md`).

### Settings

Add to `convergence_games/settings.py`:

```python
ACCESS_TOKEN_TTL_MINUTES: int = 15
REFRESH_TOKEN_TTL_DAYS: int = 180
REFRESH_ROTATION_GRACE_SECONDS: int = 5  # tolerate a recently-rotated jti to absorb concurrent-refresh races
```

`TOKEN_SECRET` continues to be a single secret shared between access and refresh JWTs. Splitting it adds env-var sprawl with little marginal benefit (refresh tokens are validated server-side via the DB regardless).

### Token classes

`convergence_games/app/request_type.py` updates `CustomToken`:

```python
@dataclass
class CustomToken(Token):
    token_type: Literal["access", "refresh", "legacy"] = "legacy"
```

The `flag: bool = False` field is removed (unused). `token_type` defaults to `legacy` so a decoded legacy `token` (no `token_type` claim) still parses cleanly via `Token.decode`'s `extras` handling — the field is read out of `extras` in `__post_init__` if present:

```python
def __post_init__(self) -> None:
    super().__post_init__()
    raw = self.extras.pop("token_type", None)
    if raw in ("access", "refresh"):
        self.token_type = raw
```

`build_token_extras` (`jwt_cookie_auth.py:20`) is unchanged in shape — it still produces the per-user claims dict. A new helper `_access_extras(user, event_roles)` wraps it and adds `"token_type": "access"`. Refresh tokens carry only `sub`, `jti`, `exp`, `iat` and `extras={"token_type": "refresh"}`.

### Middleware

Replace `LaxJWTCookieAuthenticationMiddleware` (`jwt_cookie_auth.py:55`) with `TokenSessionAuthenticationMiddleware` that subclasses `JWTCookieAuthenticationMiddleware`. It overrides `authenticate_request` and wraps the ASGI `send` callable so it can inject `Set-Cookie` headers when it refreshes/migrates/revokes.

Roughly:

```python
class TokenSessionAuthenticationMiddleware(JWTCookieAuthenticationMiddleware):
    async def authenticate_request(self, connection):
        access_cookie = connection.cookies.get("access")
        refresh_cookie = connection.cookies.get("refresh")
        legacy_cookie = connection.cookies.get("token")

        # Hot path: valid access token.
        if access_cookie:
            try:
                token = self._decode(access_cookie)
                if token.token_type == "access":
                    user = _user_from_token_claims(int(token.sub), token.extras)
                    user_id_ctx.set(user.id)
                    return AuthenticationResult(user=user, auth=token)
            except NotAuthorizedException:
                pass  # fall through to refresh path

        # Refresh path.
        if refresh_cookie:
            return await self._authenticate_via_refresh(connection, refresh_cookie)

        # Legacy migration path.
        if legacy_cookie:
            return await self._authenticate_via_legacy(connection, legacy_cookie)

        return AuthenticationResult(user=None, auth=None)
```

The Lax behaviour today (catching `NotAuthorizedException` and returning a `(None, None)` result) is preserved by wrapping the entire body in `try/except NotAuthorizedException` and returning the unauthenticated result on any failure.

#### Cookie injection from middleware

Middleware can't return a `Response`, so it has to inject `Set-Cookie` headers via the ASGI `send` wrapper. Pattern:

```python
async def __call__(self, scope, receive, send):
    pending_cookies: list[Cookie] = []
    scope.setdefault("state", {})["pending_auth_cookies"] = pending_cookies
    async def wrapped_send(message):
        if message["type"] == "http.response.start" and pending_cookies:
            headers = list(message.get("headers", []))
            for cookie in pending_cookies:
                headers.append((b"set-cookie", cookie.to_header().encode("latin-1")))
            message = {**message, "headers": headers}
        await send(message)
    await super().__call__(scope, receive, wrapped_send)
```

`_authenticate_via_refresh`, `_authenticate_via_legacy`, and the explicit logout endpoints append to `connection.scope["state"]["pending_auth_cookies"]`. Cookie `Cookie.to_header()` is the existing `litestar.datastructures.Cookie` API.

#### `_authenticate_via_refresh`

1. Decode JWT; if invalid or `token_type != "refresh"` → unauthenticated.
2. Look up `user_session` by `jti`. If not found → unauthenticated, clear cookies.
3. If `revoked_at` is set:
   - If `revoked_reason == "rotated"` and `now < revoked_at + REFRESH_ROTATION_GRACE_SECONDS` → tolerate (concurrent-refresh race); read the active sibling row (`SELECT * FROM user_session WHERE family_id = :fid AND revoked_at IS NULL`) and proceed using its `jti` for the new access token without rotating again.
   - Otherwise → reuse detected: `UPDATE user_session SET revoked_at=now(), revoked_reason='reuse_detected' WHERE family_id = :fid AND revoked_at IS NULL`. Clear cookies. Unauthenticated.
4. If `expires_at < now` → revoke this row, clear cookies, unauthenticated.
5. Load `User` + `event_roles` (`selectinload(User.event_roles)`).
6. Mint new access token (`exp = now + ACCESS_TOKEN_TTL_MINUTES`). Append access cookie.
7. Rotate refresh: insert new `user_session` row with same `family_id`, fresh `jti`, fresh `expires_at = now + REFRESH_TOKEN_TTL_DAYS`. Mark previous row `revoked_at=now, revoked_reason='rotated'`. Append new refresh cookie. (Skip rotation in the grace-window branch above.)
8. Update `last_used_at = now` on the active row (or the sibling, in the grace branch).
9. Return `AuthenticationResult(user, auth=access_token)`.

DB writes happen on a fresh `AsyncSession` opened from `connection.app.state.db_engine` (matching `retrieve_user_handler`'s pattern in `jwt_cookie_auth.py:38`), wrapped in `async with session.begin():` so it commits on success.

#### `_authenticate_via_legacy`

1. Decode legacy JWT (same secret, `verify_expiry=True`). If `token_type` claim is set (i.e. it's actually one of the new tokens) → fall through to normal access/refresh paths (handled earlier). If decode fails → unauthenticated, clear `token`.
2. Reconstruct the `User` from the legacy claims (current `_user_from_token_claims` logic). If extras are empty, fall back to DB load (same as today).
3. Issue a fresh access + refresh pair via `_issue_login_session(user, event_roles, request)` — see helper below. Append both cookies.
4. Append a `Cookie(key="token", max_age=0)` to delete the legacy cookie.
5. Return the user as authenticated for this request.

After one successful migration, the legacy decode path is never invoked for that browser again.

### Issuer helper

`_issue_login_session(user, event_roles, *, user_agent, ip, transaction) -> tuple[Cookie, Cookie]` lives next to `build_token_extras` in `jwt_cookie_auth.py`. Returns the access + refresh `Cookie` instances and inserts the `user_session` row. Used by:

- `convergence_games/app/common/auth.py:authorize_flow` — replaces the `jwt_cookie_auth.login(...)` call at line 195. The function signature evolves to return cookies and the controller attaches them to the redirect.
- `convergence_games/app/routers/frontend/profile.py:post_profile` — replaces the `jwt_cookie_auth.login(...)` call at line 264.
- The middleware's legacy-migration path (above).

For external API consumers there is no API at present that mints tokens, so a separate `Authorization: Bearer` flow is out of scope.

### Logout

`OAuthController.post_logout` (`convergence_games/app/routers/frontend/oauth.py:164`) gains a `transaction: AsyncSession` and a `request: Request`. It:

1. Reads the refresh cookie. If present and decodes, marks the matching `user_session` row `revoked_at=now, revoked_reason='logout'`.
2. Calls `response.delete_cookie("access")`, `response.delete_cookie("refresh")`, `response.delete_cookie("token")` (legacy).
3. Returns the existing redirect.

`POST /auth/logout-everywhere` (new handler on a new `AuthController` in `convergence_games/app/routers/frontend/auth.py`) does the same revoke + cookie clear, but the SQL revokes every active row for `request.user.id` (`UPDATE user_session SET revoked_at=now(), revoked_reason='logout_everywhere' WHERE user_id = :uid AND revoked_at IS NULL`).

### Sessions UI

Add a panel to `convergence_games/app/templates/pages/profile.html.jinja` that calls into a new `Sessions` component:

- `convergence_games/app/templates/components/Sessions.html.jinja` — takes `sessions: list[UserSessionView]` and `current_session_jti: str`. Each row shows: parsed UA (browser + OS), created (relative time, with absolute on hover via existing `nice_time_format`), last seen, "this device" badge if `session.jti == current_session_jti`, and a revoke button (`hx-post="/auth/sessions/{sqid}/revoke"`). Plus a footer button: "Sign out everywhere".

Profile route (`get_profile` in `convergence_games/app/routers/frontend/profile.py:230`) loads sessions and current jti when rendering. The current jti is exposed via `request.scope["state"]["current_session_jti"]`, set by the middleware on every authenticated request.

User-Agent parsing uses a small inline regex helper in `convergence_games/utils/user_agent.py` that extracts a coarse "browser / OS" string — sufficient for display. Promote to `ua-parser` (or similar) as a follow-up only if real-world UAs prove difficult to handle.

No IP capture — only the User-Agent string is recorded. Privacy minimisation; the displayed browser/OS is enough to let users recognise their own sessions.

Endpoints (in the new `AuthController`):

- `POST /auth/sessions/{session_sqid:str}/revoke` — guards: `user_guard`. Decodes sqid. Verifies the row belongs to `request.user.id` (return 404 otherwise — don't leak IDs). Marks row revoked with reason `'admin'` (if revoking another session) or `'logout'` (if revoking the current device — though logging out via the navbar is the more natural path for self). Returns the updated sessions panel block via `HTMXBlockTemplate`.
- `POST /auth/logout-everywhere` — guards: `user_guard`. Revokes every row for the user. Clears all three cookies. Returns a `ClientRedirect("/sign-in")`.

`AuthController` is registered in `convergence_games/app/routers/frontend/__init__.py` alongside `OAuthController` and friends.

### Logout

The existing `OAuthController.post_logout` keeps its `/oauth2/logout` URL for backwards compatibility but its body switches to revoking the current session row. A small refactor extracts the session-revoke + cookie-clear logic into `convergence_games/app/common/auth.py:logout_current_session(transaction, request, response)` so the navbar logout and the `AuthController` logout handlers share code.

### Connection / scope plumbing

The middleware sets, per request:

- `scope["state"]["current_session_jti"]` — the jti of the session row that authenticated this request (None if access-cookie-only without refresh, which only happens for the first request after migration).
- `scope["state"]["pending_auth_cookies"]` — list of cookies to append to the response.

`request.user.id` keeps coming from the access-token claims. Nothing else in the codebase needs to change.

## Implementation Plan

### Phase 1: Data model + settings

- [ ] **Add `UserSession` model** (`convergence_games/db/models.py`)
  - Columns per Technical Design. Place near `UserLogin` for grouping.
  - Add `__all__` updates if the file uses one.
- [ ] **Add settings** (`convergence_games/settings.py`)
  - `ACCESS_TOKEN_TTL_MINUTES: int = 15`
  - `REFRESH_TOKEN_TTL_DAYS: int = 180`
  - `REFRESH_ROTATION_GRACE_SECONDS: int = 5`
- [ ] **Generate migration** (`convergence_games/migrations/versions/<date>_add_user_session_<rev>.py`)
  - `litestar --app convergence_games.app:app database make-migrations -m "add user_session table"`
  - Verify the generated DDL: `user_session` table with all columns + indexes on `user_id`, `jti` (unique), `family_id`.
- [ ] **Add UserSession sqid salt** (no code change required — `_ink()` salts by class name automatically; verify by importing and calling `swim` in a REPL).

#### Phase 1 verification

- [ ] `basedpyright` — clean
- [ ] `ruff check` — clean
- [ ] `litestar --app convergence_games.app:app database upgrade` succeeds against the dev DB.
- [ ] Manual: connect via DbGate, confirm the `user_session` table exists with the expected columns + indexes.

### Phase 2: Token middleware + issuer helper (no behaviour change for issuance yet)

- [ ] **Update `CustomToken`** (`convergence_games/app/request_type.py`)
  - Drop `flag: bool = False`.
  - Add `token_type: Literal["access", "refresh", "legacy"] = "legacy"` with `__post_init__` lifting `extras["token_type"]` if present.
- [ ] **Refactor `jwt_cookie_auth.py`** (`convergence_games/app/app_config/jwt_cookie_auth.py`)
  - Keep the `jwt_cookie_auth` `JWTCookieAuth` instance (used for `on_app_init` registration in `app.py:26`). Change its cookie key to `access`, `default_token_expiration=timedelta(minutes=SETTINGS.ACCESS_TOKEN_TTL_MINUTES)`.
  - Replace `LaxJWTCookieAuthenticationMiddleware` with `TokenSessionAuthenticationMiddleware` per Technical Design.
  - Add `_access_extras(user, event_roles)`, `_issue_login_session(...)`, `_revoke_session_by_jti(...)`, `_revoke_family(...)` helpers.
  - Add `make_access_cookie(token: str, ttl: timedelta) -> Cookie`, `make_refresh_cookie(token: str, ttl: timedelta) -> Cookie`, `make_legacy_clear_cookie() -> Cookie` factories.
  - `__call__` wraps `send` to inject pending cookies (per Technical Design).
- [ ] **Plumb middleware state** (`convergence_games/app/app_config/jwt_cookie_auth.py` + `convergence_games/app/request_type.py`)
  - Set `scope["state"]["current_session_jti"]` in the middleware on the access path (decoded from the access token's `jti`) and refresh path (the active session row's `jti`).
  - No type-level change to `Request` — controllers read via `request.scope["state"].get(...)`.

#### Phase 2 verification

- [ ] `basedpyright` — clean
- [ ] `ruff check` — clean
- [ ] App starts: `litestar --app convergence_games.app:app run --reload` boots without import errors.
- [ ] Manual: with no cookies, every page still loads as anonymous (Lax behaviour preserved).
- [ ] Manual: log in via existing legacy path (still emitting `token`); confirm requests still authenticate (legacy decode path runs).

### Phase 3: Switch issuance to access + refresh

- [ ] **Replace login call sites** (`convergence_games/app/common/auth.py:195`, `convergence_games/app/routers/frontend/profile.py:264`)
  - Both now call `_issue_login_session(user, event_roles, user_agent=request.headers.get("user-agent"), transaction=transaction)`.
  - `authorize_flow` returns the redirect with `cookies=[access_cookie, refresh_cookie, legacy_clear_cookie]`. The legacy-clear cookie ensures any old session in the same browser stops getting the legacy code path next request.
  - `post_profile` mirrors the same — appends both cookies + clear cookie to the response.
- [ ] **Decide Phase-3 cutover** — at this point new logins emit access + refresh. Existing logged-in browsers still hold a legacy `token`; on their next request, the middleware's legacy-migration path runs and they get upgraded. No forced logouts.
- [ ] **Verify legacy migration** in dev
  - With a browser holding a legacy `token` cookie (capture before deploy), open the dev server. Confirm: response sets `access` and `refresh`, deletes `token`. Confirm a `user_session` row was created.

#### Phase 3 verification

- [ ] `basedpyright` — clean
- [ ] `ruff check` — clean
- [ ] Manual: fresh login (clear cookies → sign in via email-magic-link). Inspect cookies in devtools → `access` and `refresh` are present, no `token`. `user_session` row exists with the user's id.
- [ ] Manual: simulate access expiry (clear `access` cookie only). Reload page. Confirm a new `access` cookie + a new `refresh` cookie (rotated `jti`) are set. `user_session` table shows two rows for the family — old `revoked_reason='rotated'`, new active.
- [ ] Manual: clear all cookies. Anonymous browsing works.
- [ ] Manual: with a captured legacy `token` cookie installed, request any page. Confirm cookies are upgraded to `access`/`refresh`, legacy `token` is cleared, `user_session` row exists.

### Phase 4: Logout + revocation endpoints

- [ ] **Refactor logout** (`convergence_games/app/routers/frontend/oauth.py:164`)
  - Inject `transaction: AsyncSession` and `request: Request`.
  - Decode refresh cookie (if any); revoke matching row with `revoked_reason='logout'`.
  - Delete `access`, `refresh`, `token` cookies on the redirect response.
  - Extract shared logic into `convergence_games/app/common/auth.py:logout_current_session(...)`.
- [ ] **Create `AuthController`** (`convergence_games/app/routers/frontend/auth.py`)
  - `POST /auth/logout-everywhere` (guards `user_guard`): revoke all active rows for `request.user.id`; clear cookies; respond with `ClientRedirect("/sign-in")`.
  - `POST /auth/sessions/{session_sqid:str}/revoke` (guards `user_guard`):
    - `sink_upper(session_sqid)` (or `sink` if lowercase) → row id.
    - `select(UserSession).where(UserSession.id == row_id, UserSession.user_id == request.user.id)` → 404 on miss.
    - Mark revoked (`revoked_reason='admin'`).
    - Re-render the sessions block via `HTMXBlockTemplate`.
- [ ] **Register controller** (`convergence_games/app/routers/frontend/__init__.py`)
  - Import `AuthController`, add to `route_handlers` list.
- [ ] **Reuse-detection middleware path** — already implemented in Phase 2; verify here with a manual replay test (curl with a previously-rotated refresh `jti`).

#### Phase 4 verification

- [ ] `basedpyright` — clean
- [ ] `ruff check` — clean
- [ ] Manual: log in, click navbar logout, confirm: row revoked (`revoked_reason='logout'`), all three cookies cleared, anonymous next request.
- [ ] Manual: log in on two browsers (or normal + incognito). Capture refresh `jti` from browser A. Hit refresh on browser A. Reuse the previous refresh (manually replay the previous cookie value via curl). Confirm: every active row in browser A's family is revoked with `revoked_reason='reuse_detected'`. Browser B unaffected.

### Phase 5: Sessions UI on profile

- [ ] **Add User-Agent helper** (`convergence_games/utils/user_agent.py`)
  - `parse_user_agent(ua: str | None) -> tuple[str, str]` returning `(browser, os)`. Inline regex over the common patterns; fall back to `("Browser", "Unknown")` on parse failure.
  - Test fixtures cover Chrome/Firefox/Safari on macOS/Windows/Linux/iOS/Android.
- [ ] **Update profile route** (`convergence_games/app/routers/frontend/profile.py:render_profile`)
  - Load active sessions for the user: `select(UserSession).where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None)).order_by(UserSession.last_used_at.desc())`.
  - Pull `current_session_jti` from `request.scope["state"]`.
  - Pass `sessions` and `current_session_jti` to the template.
- [ ] **Add Sessions component** (`convergence_games/app/templates/components/Sessions.html.jinja`)
  - Table-style list: row per session showing browser + OS (via `parse_user_agent`), created (relative), last seen (relative), "this device" badge, revoke button (`hx-post="/auth/sessions/{{ session | swim_upper }}/revoke"`, `hx-target="#sessions-panel"`).
  - Footer "Sign out everywhere" button: `hx-post="/auth/logout-everywhere"`.
- [ ] **Embed in profile page** (`convergence_games/app/templates/pages/profile.html.jinja`)
  - Add a new section below existing profile content: `<Sessions sessions={{ sessions }} current_session_jti={{ current_session_jti }} />`. Wrap in `<div id="sessions-panel">` so HTMX can target it.

#### Phase 5 verification

- [ ] `basedpyright` — clean
- [ ] `ruff check` — clean
- [ ] `npx tsc --noEmit` — clean (no TS depended on the old auth)
- [ ] Manual: load `/profile` after logging in, confirm Sessions panel renders, "this device" indicator points at the right row.
- [ ] Manual: log in on a second browser. Refresh `/profile` on browser A — second session appears.
- [ ] Manual: revoke browser B's session from browser A. On browser B's next request, middleware sees the revoked row, treats it as unauthenticated, and the cookies clear.
- [ ] Manual: "Sign out everywhere" on browser A logs out everywhere; both browsers anonymous on next request.

### Phase 6: Tests + cleanup

- [ ] **Unit tests for token middleware** (`tests/app/app_config/test_token_middleware.py`)
  - Use the same `sqlite+aiosqlite` in-memory fixture pattern as `tests/app/common/test_auth.py`.
  - Build a `MockASGIConnection` (or use Litestar's testing utilities) that delivers cookies and captures Set-Cookie output.
  - Cases: access valid (no DB hit), access expired + refresh valid (rotation happens, cookies emitted), refresh re-use (family revoked), refresh expired (cookies cleared), legacy only (migration path), no cookies (anonymous), grace-window concurrent refresh.
- [ ] **Unit tests for issuer helper** (extend `tests/app/common/test_auth.py`)
  - `authorize_flow(SIGN_UP)` → emits both new cookies, creates user_session row.
  - `authorize_flow(SIGN_IN)` → same.
  - `authorize_flow(LINK)` → same.
- [ ] **Unit tests for revocation** (`tests/db/test_user_session.py`)
  - `_revoke_session_by_jti` marks row revoked.
  - `_revoke_family` revokes only active rows in the family.
- [ ] **Unit tests for User-Agent helper** (`tests/utils/test_user_agent.py`)
  - Covers Chrome/Firefox/Safari/Edge across mac/win/linux/iOS/Android, plus an unknown UA.
- [ ] **End-to-end manual run-through** in dev (browser, real cookies):
  1. Sign up fresh account → access + refresh emitted, `user_session` row created.
  2. Wait 16 minutes (or shorten `ACCESS_TOKEN_TTL_MINUTES` to 1 for the test) → next request silently mints new access + refresh.
  3. Admin grants the user a new `UserEventRole` (via the event manager). Wait one access TTL → user's UI reflects the new role without sign-out.
  4. Logout from navbar → row revoked, cookies cleared.
  5. Two browsers signed in → revoke browser B from browser A → browser B's next request becomes anonymous.
  6. "Sign out everywhere" → both browsers anonymous.
  7. Restore a captured pre-rollout legacy `token` cookie → next request silently upgrades, `token` cleared, access + refresh issued, `user_session` row created.
  8. Replay a rotated refresh cookie via curl → family-wide revoke, both real browsers anonymous, audit row shows `revoked_reason='reuse_detected'`.

#### Phase 6 verification

- [ ] `pytest` — all tests passing
- [ ] `basedpyright` — clean
- [ ] `ruff check` — clean
- [ ] `npx tsc --noEmit` — clean

## Acceptance Criteria

- [ ] `pytest` clean, including new middleware, helper, and User-Agent tests
- [ ] `basedpyright` clean
- [ ] `ruff check` clean
- [ ] `npx tsc --noEmit` clean
- [ ] Migration `add user_session table` applies cleanly; downgrade reverses it
- [ ] After fresh login, browser holds `access` + `refresh` cookies (HttpOnly), no legacy `token` cookie
- [ ] Clearing only the `access` cookie and reloading silently re-issues both cookies and rotates the refresh `jti` (verified via DbGate)
- [ ] An access token with TTL set to 1 minute observably refreshes around the 1-minute mark with no UX disruption
- [ ] Admin granting a `UserEventRole` propagates to the affected user's UI within one access TTL with no manual logout
- [ ] Replaying a rotated refresh cookie (curl) revokes the entire family and clears the cookies on the response
- [ ] Browsers holding a pre-deploy legacy `token` cookie continue to authenticate and are upgraded transparently to `access` + `refresh` on first request
- [ ] `/profile` shows a Sessions panel with parsed UA, created, last seen, "this device" badge; per-row revoke and "Sign out everywhere" both work
- [ ] Logging out from the navbar clears all three cookies and revokes only the current session row (other browsers remain signed in)

## Risks and Mitigations

1. **Concurrent-refresh race revokes a legitimate user**: two tabs hit the server simultaneously, both find the access expired and try to rotate the refresh; the second one sees a `rotated` row and could trigger reuse-detection. Mitigation: `REFRESH_ROTATION_GRACE_SECONDS` window (5 s) where the just-rotated `jti` is tolerated and the request uses the active sibling row instead of rotating again.
2. **Cookie-injection from middleware breaks if a controller already wrote `Set-Cookie`**: duplicate `Set-Cookie` headers are valid HTTP but a controller could overwrite ours. Mitigation: append to the existing header list rather than replace; keep the access/refresh cookie names distinct from anything controllers set today.
3. **Backwards-compat path stays around forever**: after the legacy 365-day TTL has expired (1 year post-deploy), every browser will have rotated; we should remove the legacy-decode path. Mitigation: tag `_authenticate_via_legacy` with a `# TODO(legacy-token-cleanup): remove after <date+365 days>` comment plus a follow-up task entry.
4. **`user_session.last_used_at` write storm**: every refresh writes one row. With a 15-min access TTL, that's at most 4 writes/hour/active-user — fine. But if we ever shorten access TTL, the rate scales. Mitigation: documented in the settings comments; consider batching/throttling later if needed.
5. **User-Agent parser brittleness**: an unrecognised UA shows "Browser / Unknown". Mitigation: helper falls back gracefully; switching to `ua-parser` is a small follow-up if needed.
6. **`scope["state"]` plumbing leaks across requests**: Litestar gives each request a fresh `scope["state"]` dict. Mitigation: confirmed by Litestar's per-request scope semantics; tested by unit tests that two concurrent requests don't see each other's pending cookies.
7. **Sqid for `UserSession.id` exposed in revoke URLs**: a logged-in user could enumerate IDs to probe other users' sessions. Mitigation: revoke endpoint returns 404 (not 403) when the row's `user_id != request.user.id`, so enumeration leaks nothing beyond "row exists or not for me".

## Notes

- Decision: keep `TOKEN_SECRET` as a single shared secret for both access and refresh JWTs. Splitting adds env-var sprawl; refresh tokens are validated server-side via the DB so the cryptographic blast radius from a leaked secret is already bounded by the rotation window.
- Decision: legacy `token` decode path remains indefinitely; remove in a follow-up task scheduled at deploy date + 12 months.
- Decision: no `User.roles_invalidated_at` shortcut — 15 min worst-case propagation is acceptable.
- Decision: refresh cookie `path=/` (not `/auth/refresh`) so the middleware can transparently refresh on any request without a frontend interceptor. Tightening to a scoped path is a future consideration.
- Decision: User-Agent parsing uses an inline regex helper first; promote to the `ua-parser` library only if real-world UAs prove difficult to handle.
- Decision: no IP capture or geo lookup. Browser/OS from User-Agent alone is enough for users to recognise their own sessions; storing IPs adds privacy/audit obligations we don't need to take on right now.
- Follow-up: remove the legacy decode path after the legacy TTL window has expired in the wild.
