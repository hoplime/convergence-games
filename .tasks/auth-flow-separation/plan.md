---
title: Separate sign-up and sign-in flows + fix email handling
created: 2026-04-18
status: in-progress
---

# Separate sign-up and sign-in flows + fix email handling

## Context

The current login experience conflates "sign in" and "sign up". Submitting any email at `/email_sign_in` sends a verification code, and `authorize_flow()` (`convergence_games/app/common/auth.py:30`) silently creates a `User` whenever the `(provider, provider_user_id)` lookup misses. Users intending to sign in to an existing Google-linked account end up with a brand-new email-only account; users typing the same Gmail address sometimes via Google OAuth and sometimes via email end up with two unrelated `User` records. There is no email normalisation anywhere — `Foo@example.com`, `foo@example.com`, and ` foo@example.com ` all resolve to distinct `UserLogin` rows because the unique key is `(provider, provider_user_id)` on raw strings.

The intended outcome:

- The user is always asked to choose **Sign up** or **Sign in** before they enter an email or pick an OAuth provider; the backend enforces that choice rather than silently doing both.
- A sign-in attempt for an unknown email never auto-creates an account — the user verifies email ownership first, then explicitly chooses *create new* or *link to an existing OAuth account*.
- A sign-up attempt for an already-known email is rejected with a friendly redirect to the sign-in flow before any code is sent.
- All email lookups, storage, and uniqueness comparisons happen on the trimmed-and-lowercased form, eliminating case- and whitespace-driven duplicates.
- A user who already has an EMAIL account at `foo@gmail.com` and signs in with the matching Google account gets the Google login auto-linked to the existing user (Google's `email_verified` is trusted because Google asserts it and the ID token's `aud` is verified).
- Discord/Facebook OAuth callbacks that surface a matching email prompt the user to confirm linking instead of either silently merging or silently creating a duplicate.
- A detection script lets operators see existing duplicates so they can manually reassign logins later.

## Requirements

- A combined `/sign-up` / `/sign-in` page presents sign-up by default with a clearly labelled "Already have an account? Log in" toggle, and the chosen mode is propagated to the backend.
- `authorize_flow()` no longer creates a `User` implicitly. The intent (`SIGN_UP`, `SIGN_IN`, `LINK`) is an explicit parameter and the function fails or returns a "needs branching" outcome when the lookup result does not match the intent.
- Submitting the sign-up form for an email or OAuth identity that already resolves to a known user blocks before sending any verification code and renders an "account exists, sign in instead" message that switches the form to sign-in mode preserving the entered email.
- Submitting the sign-in form for an unknown email still sends a code (no email enumeration) but, after successful code verification, lands the user on a "no account found" screen offering "Create new account" or "Sign in with Google/Discord/Facebook to link this email to that account".
- The "link this email" flow round-trips through OAuth carrying a short-lived signed token that captures the verified email; on return, an `EMAIL` `UserLogin` is attached to the OAuth user.
- Email normalisation (`.strip().lower()`) is applied at every write site (form post, OAuth `provider_email` capture, `UserEmailVerificationCode` insert, `EMAIL` `UserLogin.provider_user_id`) and every read site (verification-code lookup, cross-provider email match).
- Google OAuth: when callback returns `email_verified=True` and the lowercased email matches an existing user's `EMAIL` login or any `provider_email`, attach the new Google `UserLogin` to that user without prompting.
- Discord/Facebook OAuth: when callback returns and the lowercased email matches an existing user, render a "Link this Discord/Facebook account to your existing account?" confirmation page; on Yes, link; on No, create a new user with the OAuth login only (the current default behaviour for that provider).
- A new `scripts/find_duplicate_users.py` lists users whose lowercased email matches another user's, grouped, with all `UserLogin` rows shown, and exits with a non-zero status if duplicates exist (so it is usable in CI/manual checks).
- No new global uniqueness DB constraint is added in this task. The plan documents which constraint(s) to consider once operators have manually reconciled existing duplicates.
- All existing callers of `authorize_flow()` are updated; no silent-create code path remains.

## Technical Design

### Intent-driven `authorize_flow`

`authorize_flow()` (`convergence_games/app/common/auth.py:30`) becomes intent-aware. Add:

```python
class AuthIntent(StrEnum):
    SIGN_UP = "sign_up"     # caller asserts "no existing account expected"
    SIGN_IN = "sign_in"     # caller asserts "existing account expected"
    LINK = "link"           # caller asserts "attach this provider to a known user"
```

`authorize_flow(..., intent: AuthIntent, ...)` returns a `Redirect` on the happy path (matches today's signature) but raises an `AuthFlowOutcome` exception subclass for the new branches the controllers need to render:

- `AccountAlreadyExistsError` — sign-up intent but the `(provider, provider_user_id)` lookup hit. Carries the matched provider for the message ("an account using this email already exists, sign in instead"). Email pre-check should normally prevent this, but it's the safety net.
- `NoAccountForSignInError` — sign-in intent and no matching login exists; carries the verified email and verified-provider info so the controller can render the "create or link" screen.
- `LinkConfirmationRequiredError` — OAuth (Discord/Facebook) callback found a cross-provider email match; carries the candidate `User` id and the proposed `UserLogin` payload so the controller can render the confirm screen.

The cross-provider email match lookup lives in a new helper `find_user_by_email(transaction, email)` that scans `UserLogin.provider_email` (and `provider_user_id` for `EMAIL`) on the lowercased value. Returns the matched `User` or `None`. If multiple match (existing duplicates), prefer the user with an `EMAIL` login, then earliest `created_at` — and emit a `print(...)` warning. (Long term, the duplicate-detection script flags these so operators reconcile.)

Auto-link decision is owned by the OAuth controller, not `authorize_flow`:

- Google: when `payload["email_verified"]` is true and `find_user_by_email` returns a user, the controller calls `authorize_flow(..., intent=AuthIntent.LINK, linking_account_id=user.id)` directly, no extra UI.
- Discord/Facebook: controller catches `LinkConfirmationRequiredError` (raised when intent would otherwise be `SIGN_UP` and `find_user_by_email` returns a hit) and renders the link-confirm page. The confirm page POSTs back with the encoded pending-OAuth payload (see below) and either `link=true` or `link=false`.

### Email normalisation

Add `convergence_games/utils/email.py` with:

```python
def normalize_email(value: str) -> str:
    return value.strip().lower()
```

Apply at:

- `PostEmailSignInForm` — normalise `email` in the controller before any use (`convergence_games/app/routers/frontend/profile.py:99`). Or push normalisation into `event_email_sign_in` (`convergence_games/app/events.py:18`) — chosen: normalise in the controller so the value persisted into `UserEmailVerificationCode.email` is already canonical.
- `event_email_sign_in` — normalise defensively at entry as well; the value is what gets stored in `UserEmailVerificationCode.email` and what magic-link emails address.
- `login_with_email_and_code` (`convergence_games/app/routers/frontend/email_auth.py:20`) — normalise `email` before the `UserEmailVerificationCode` lookup and before passing into `authorize_flow`.
- `UserEmailVerificationCode.decode_magic_link_code` — normalise email after decoding (in `login_with_email_and_code`, not in the model — keep the model dumb).
- OAuth controllers (`convergence_games/app/routers/frontend/oauth.py:198`) — normalise `profile_info.user_email` after `provider.get_profile_info()`.

For the `EMAIL` provider specifically, `provider_user_id` is the email itself (`email_auth.py:42`). Normalise it the same way so the existing `(provider, provider_user_id)` unique constraint becomes effectively case-insensitive for new rows.

### Pending verified-email token

For the "sign in for unknown email then link via OAuth" flow, the verified email needs to survive an OAuth round-trip. Reuse the existing fernet pattern from `OAuthRedirectState` (`convergence_games/app/common/auth.py:100`) by extending it with a `pending_verified_email: str | None = None` field. When set, the OAuth `authorize` callback knows: after resolving the OAuth identity, also create an `EMAIL` `UserLogin` for the verified email and attach to the same user.

This avoids a second persistence model and stays within the existing 365-day-cookie/short-lived-token discipline. The token is fernet-signed already.

### UI changes

Replace the current dual-purpose `register.html.jinja` + `email_sign_in.html.jinja` with a unified flow:

1. **`pages/auth.html.jinja`** (new) — the combined sign-up/sign-in page. Takes `mode: Literal["sign_up", "sign_in"]` (default `sign_up`). Renders:
   - Title: "Create an account" or "Sign in".
   - Email form with `mode` baked in as a hidden field (and reflected in the submit URL — see routes).
   - OAuth buttons (Email/Google/Discord) — buttons themselves carry the mode in their URLs.
   - Footer link to switch mode: "Already have an account? Sign in" / "Don't have an account? Sign up". Switching preserves any entered email via query parameter.
2. **`components/forms/sign_in_buttons/Email.html.jinja`, `Google.html.jinja`, `Discord.html.jinja`** — accept a new `mode` prop and include it in their URLs (`/sign-up/email`, `/sign-in/email`, `/oauth2/google/login?mode=sign_up`, etc.). Label flips ("Sign up with X" vs "Sign in with X"). The existing linking-account variant is preserved.
3. **`components/AccountExists.html.jinja`** (new) — rendered as the response to a sign-up POST when the email already resolves to an account. Shows "An account already exists for `<email>`. Sign in instead?" and links back to the sign-in page with the email prefilled.
4. **`components/VerifyCode.html.jinja`** — extend with `mode` so the form POSTs to a mode-aware verify endpoint (so the controller knows the user's intent at code-verification time).
5. **`components/NoAccountFound.html.jinja`** (new) — rendered after a sign-in code is verified but no user exists at that email. Shows the verified email and two CTAs:
   - "Create a new account" — POSTs to a "promote verified email to new account" endpoint.
   - "I already have an account — sign in to link this email": three OAuth-provider link buttons that initiate the OAuth round-trip with the pending-email token populated.
6. **`components/LinkOAuthAccount.html.jinja`** (new) — rendered when an OAuth callback (Discord/Facebook) finds a matching email. Shows "We found an existing account for `<email>` (linked via X). Link your Discord/Facebook account to it?" with confirm/decline buttons. Confirm POSTs the encoded pending-OAuth payload back to a `/oauth2/link_confirm` endpoint.

Tear down dead UI:

- `pages/register.html.jinja` — replaced; delete after migration.
- `pages/email_sign_in.html.jinja` — replaced; delete after migration.
- `render_profile()` (`convergence_games/app/routers/frontend/profile.py:38`) — currently routes unauthenticated users to `pages/register.html.jinja`; switch it to `pages/auth.html.jinja` with `mode="sign_up"` and the `invalid_action_path` carry-over.

### Routes

Replace the single `GET/POST /email_sign_in` with mode-aware routes. URL design:

- `GET /sign-up` and `GET /sign-in` → render `pages/auth.html.jinja` with the appropriate mode. Both accept optional `email` query (for prefill) and `redirect_path`.
- `POST /sign-up/email` → pre-check via `find_user_by_email`. If user exists, render `AccountExists`. If not, emit `EVENT_EMAIL_SIGN_IN` with `mode=sign_up` and render `VerifyCode` carrying mode.
- `POST /sign-in/email` → always emit `EVENT_EMAIL_SIGN_IN` (no enumeration); render `VerifyCode` with `mode=sign_in`.
- `POST /email_auth/verify_code` → existing handler, extended: read `mode` from form/state. Verify code as today, then:
  - `mode=sign_up`: call `authorize_flow(intent=SIGN_UP)`. On `AccountAlreadyExistsError` (race), render `AccountExists`.
  - `mode=sign_in`: call `authorize_flow(intent=SIGN_IN)`. On `NoAccountForSignInError`, render `NoAccountFound` with the verified email encoded into a fresh signed `OAuthRedirectState(pending_verified_email=email, ...)` token usable by the linking buttons.
- `GET /email_auth/magic_link` → infer mode from the encoded state (default `SIGN_IN` for safety — magic links are a sign-in-style affordance).
- `POST /sign-up/from-verified-email` → consume the signed token containing `pending_verified_email`, create the new user with the EMAIL `UserLogin`, log in. Used by the "Create a new account" button on `NoAccountFound`.
- `GET /oauth2/{provider}/login` → accept `mode` query, encode it (and any `pending_verified_email`) into the existing `OAuthRedirectState`. Add `OAuthRedirectState.mode: AuthIntent | None`.
- `GET /oauth2/{provider}/authorize` → on callback, decide intent from `state.mode`:
  - With `pending_verified_email`: after authorising the OAuth user (creating or matching), also attach an `EMAIL` `UserLogin` for the verified email to that user (idempotent).
  - Otherwise, intent + Google `email_verified` → silent link via `find_user_by_email` if matched.
  - Otherwise Discord/Facebook with email match → raise `LinkConfirmationRequiredError`, render `LinkOAuthAccount` and stash the OAuth-token-derived payload (provider, provider_user_id, provider_email, optional name fields, candidate user id) in a fresh signed token.
- `POST /oauth2/link_confirm` → consume the signed payload; if the user clicked confirm, attach the `UserLogin` to the candidate user via `authorize_flow(intent=LINK, linking_account_id=...)`; if declined, fall back to `authorize_flow(intent=SIGN_UP, ...)` to create a fresh user.

All new routes live in the existing controllers (`ProfileController` / `EmailAuthController` / `OAuthController`) — no new top-level controller required. `before_request_handler` (`convergence_games/app/routers/frontend/__init__.py:27`) needs updating so the new path allow-list (`/sign-up`, `/sign-in`, `/sign-up/from-verified-email`, `/oauth2/link_confirm`) does not loop redirect users with un-set-up profiles.

### Models

No schema changes. `UserLogin.provider_user_id` and `UserLogin.provider_email` keep their existing `(provider, provider_user_id)` unique constraint; the normalisation work makes that constraint effectively case-insensitive for new writes. A future task can add a unique partial index on `lower(provider_email)` (or a generated column) once operators have reconciled existing duplicates.

`UserEmailVerificationCode.email` is written normalised; lookups in `login_with_email_and_code` use the normalised value. No model change needed — the rule is enforced at every write/read site.

### Detection script

`scripts/find_duplicate_users.py` — uses the existing app/db bootstrap pattern (see `scripts/create_mock_event.py` for the pattern). Steps:

1. Open an async session.
2. Pull all `UserLogin` rows joined to `User`, with `provider_email` and (for `EMAIL`) `provider_user_id`.
3. Group by `normalize_email(...)` of the email value.
4. For any group spanning more than one `User.id`, print:
   - The lowercased email key.
   - Each user (id, full name, created_at).
   - Each `UserLogin` for that user (provider, raw `provider_user_id`, raw `provider_email`).
5. Also print groups where multiple `UserLogin` rows share an effective lowercase email under one user but with different raw casing — this surfaces accidental dupes inside one account.
6. Exit `1` if any duplicates found, else `0`. Print suggested next steps (manual reassignment) but do not modify data, per project convention (`feedback_scripts_no_automod.md`).

`argparse` for `--verbose` flag (default off, prints only summary).

## Implementation Plan

### Phase 1: Email normalisation

- [x] **Add normalisation helper** (`convergence_games/utils/email.py`)
  - Single function `normalize_email(value: str) -> str` returning `value.strip().lower()`.
  - Add module to `convergence_games/utils/__init__.py` `__all__` if that file defines one.
- [x] **Apply to email-sign-in form path** (`convergence_games/app/routers/frontend/profile.py`)
  - In `post_email_sign_in`, normalise `data.email` before passing to the event emit.
- [x] **Apply to event emitter** (`convergence_games/app/events.py:event_email_sign_in`)
  - Normalise `email` argument at entry (defensive; cheap).
- [x] **Apply to verification code lookup** (`convergence_games/app/routers/frontend/email_auth.py:login_with_email_and_code`)
  - Normalise `email` before the `UserEmailVerificationCode` query.
  - Magic link: normalise the email returned by `decode_magic_link_code` before use.
- [x] **Apply to OAuth profile capture** (`convergence_games/app/routers/frontend/oauth.py`)
  - After `provider.get_profile_info`, normalise `profile_info.user_email` (only if not None).
- [x] **Apply to email-as-provider-user-id** (`convergence_games/app/routers/frontend/email_auth.py:42`)
  - Use the normalised email for `ProfileInfo.user_id` as well (currently raw email).

#### Phase 1 verification

- [x] `ruff check` — no new errors
- [x] `basedpyright` — no new errors
- [x] Manual: enter `Foo@Example.com  ` in current sign-in form (dev env), confirm verification code lookup succeeds end-to-end and the resulting `UserLogin.provider_user_id` is `foo@example.com`.

### Phase 2: Refactor `authorize_flow` and add intent

- [x] **Add `AuthIntent` enum** (`convergence_games/app/common/auth.py`)
  - `StrEnum` with `SIGN_UP`, `SIGN_IN`, `LINK`. Place near `ProfileInfo`.
- [x] **Add outcome exception types** (same file)
  - `AccountAlreadyExistsError`, `NoAccountForSignInError`, `LinkConfirmationRequiredError`. Each carries the data the controller needs to render the next screen (matched provider; verified email; candidate user id + pending OAuth payload).
- [x] **Add `find_user_by_email`** (`convergence_games/app/common/auth.py`)
  - Async helper; queries `UserLogin` joining `User`, on lowercased `provider_email` or `provider_user_id` for `EMAIL` provider; returns first matching `User` (preferring the one with an `EMAIL` login then earliest `created_at`); prints a warning if multiple users match.
- [x] **Refactor `authorize_flow` signature** (same file)
  - Add `intent: AuthIntent` (required; no default).
  - Remove the silent-create branch when `linking_account_id is None and user_login is None`.
  - Behaviour matrix:
    - `SIGN_UP` + login already exists → raise `AccountAlreadyExistsError`.
    - `SIGN_UP` + login does not exist → create user + login as today.
    - `SIGN_IN` + login exists → log in (current behaviour).
    - `SIGN_IN` + login does not exist → raise `NoAccountForSignInError` (controllers handle the fallback).
    - `LINK` (with `linking_account_id`) + login does not exist → attach to specified user (current `linking_account_id` branch).
    - `LINK` + login exists for the same user → no-op redirect (idempotent).
    - `LINK` + login exists for a *different* user → raise `HTTPException(403)` (current "another account already linked" message, retained).
- [x] **Update all call sites of `authorize_flow`** so each passes an explicit intent
  - `convergence_games/app/routers/frontend/email_auth.py:login_with_email_and_code` — accept and forward intent. Temporary fallback: if no explicit `intent` is provided, default to `SIGN_IN` and on `NoAccountForSignInError` retry as `SIGN_UP`. Removed once Phase 5 wires the `NoAccountFound` UI.
  - `convergence_games/app/routers/frontend/oauth.py:get_provider_auth_authorize` — pick `LINK` when `linking_account_id` is set, otherwise `SIGN_IN` with the same `NoAccountForSignInError → SIGN_UP` fallback. Removed once Phase 6 wires cross-provider link confirmation.

#### Phase 2 verification

- [x] `basedpyright` — clean (1 pre-existing `BaseOAuth2` generic warning unrelated)
- [x] `ruff check` — clean
- [x] Manual: trigger each branch in dev (sign-in to existing account: success; sign-in to unknown email: still creates account via the temporary fallback — full UX comes in Phase 4/5).

### Phase 3: Cross-provider linking infrastructure

- [x] **Extend `OAuthRedirectState`** (`convergence_games/app/common/auth.py:100`)
  - Add `mode: AuthIntent | None = None` and `pending_verified_email: str | None = None`. Both round-trip via the existing fernet encode/decode.
- [x] **Add pending-OAuth-link payload model** (same file)
  - `PendingOAuthLink` `BaseModel` with `provider`, `provider_user_id`, `provider_email`, `user_first_name`, `user_last_name`, `user_profile_picture`, `candidate_user_id`. `encode/decode` via fernet (same pattern). Also carries `redirect_path` for post-link return.
- [x] **Wire `find_user_by_email` into OAuth callback** (`convergence_games/app/routers/frontend/oauth.py:get_provider_auth_authorize`)
  - When intent would be `SIGN_UP` (no `linking_account_id`, no `pending_verified_email`):
    - If `provider == GOOGLE` and `payload["email_verified"]` is true and `find_user_by_email` returns a user → call `authorize_flow(intent=LINK, linking_account_id=user.id, ...)`. **Done.**
    - Else if `provider in (DISCORD, FACEBOOK)` and `find_user_by_email` returns a user → encode a `PendingOAuthLink` and redirect to `GET /oauth2/link_confirm?payload=<token>` (which renders `LinkOAuthAccount`). **Deferred to Phase 6** (route does not exist yet); for now Discord/Facebook misses still fall through to `SIGN_UP`. Marked with `TODO(auth-flow-separation)` in the handler.
    - Else → call `authorize_flow(intent=SIGN_UP, ...)`. **Done.**
- [x] **Symmetric: EMAIL sign-in matching an existing GOOGLE account auto-links** (`convergence_games/app/routers/frontend/email_auth.py:login_with_email_and_code`)
  - On `NoAccountForSignInError` for the EMAIL provider, run `find_user_by_email`. If the matched user has any `GOOGLE` `UserLogin` whose `provider_email` matches, attach the EMAIL login via `authorize_flow(intent=LINK, linking_account_id=matched.id)`. Other matched-only providers (Discord/Facebook) fall through to the temporary SIGN_UP fallback until Phase 5/6 wires the explicit prompt.
  - When `pending_verified_email` is set in state → after OAuth user is resolved (either matched login or freshly created), also create an `EMAIL` `UserLogin(provider=EMAIL, provider_user_id=email, provider_email=email)` attached to that user if one does not already exist. **Done** via new `extra_email_to_link` parameter on `authorize_flow` and helper `_attach_email_login_if_missing`.
- [x] **Plumb Google's `email_verified` into `ProfileInfo`** (`convergence_games/app/routers/frontend/oauth.py:GoogleOAuthProvider.get_profile_info`)
  - Add `email_verified: bool = False` field to `ProfileInfo` (`convergence_games/app/common/auth.py:ProfileInfo`). Populate from `payload.get("email_verified", False)`.
  - Discord/Facebook: leave `False` (we do not trust those for silent link).

#### Phase 3 verification

- [x] `basedpyright` — clean (only pre-existing `BaseOAuth2` generic warning)
- [x] `ruff check` — clean
- [x] Manual: in dev, with an existing email-only account, complete Google sign-in for the same Gmail address; confirm a single `User` ends up with both `EMAIL` and `GOOGLE` logins. Also tested the reverse direction (existing Google-only account, email sign-in) — both link to the same user.

### Phase 4: Combined sign-up / sign-in UI

- [x] **Create `pages/auth.html.jinja`** (`convergence_games/app/templates/pages/auth.html.jinja`)
  - Accepts `mode`, `invalid_action_path`, `redirect_path`. Embeds the email form directly + Google/Discord buttons + a plain anchor toggle (no JS, no email preservation across toggle — user opted to keep it simple). `redirect_path` is propagated through the toggle URL (path-only, not the email).
- [x] **Update sign-in button components** (`convergence_games/app/templates/components/forms/sign_in_buttons/{Google,Discord}.html.jinja`)
  - Add `mode` and `redirect_path` props. URL becomes `/oauth2/{provider}/login?mode=sign_up` etc. Label flips by mode. Linking-variant unchanged. (`Email.html.jinja` left untouched — only the linking flow uses it; the auth page embeds the email form inline.)
- [x] **Add `components/AccountExists.html.jinja`**
  - Inputs: `email`. Renders an info alert + "Go to Sign In" button that GETs `/sign-in`.
- [x] **Extend `components/VerifyCode.html.jinja`**
  - Accept `mode` prop, include as hidden form field; submit-button label flips between "Sign In" and "Sign Up".
- [x] **Add new mode-aware routes** (`convergence_games/app/routers/frontend/profile.py`)
  - `GET /sign-up`, `GET /sign-in` — render `pages/auth.html.jinja`.
  - `POST /sign-up/email` — pre-check `find_user_by_email`; on hit render `AccountExists`; on miss emit `EVENT_EMAIL_SIGN_IN` (state carries `mode=SIGN_UP`) and render `VerifyCode` with `mode=sign_up`.
  - `POST /sign-in/email` — always emit (no enumeration); render `VerifyCode` with `mode=sign_in`.
  - `GET/POST /email_sign_in` left intact for the linking flow (used from `pages/profile.html.jinja`'s "Link Email" button). Removal deferred to Phase 8 once the new routes have soaked.
- [x] **Update `render_profile`** (`convergence_games/app/routers/frontend/profile.py:38`)
  - Render `pages/auth.html.jinja` (mode `sign_up`) instead of `pages/register.html.jinja`. Subsequently changed: anonymous-user branch removed; `get_profile` now redirects unauthenticated requests to `/sign-up` (using `litestar.plugins.htmx.ClientRedirect` for HTMX requests, plain `Redirect` otherwise) so the URL bar always reflects the rendered auth state. Avoids a partial-render bug where the auth page mode looked mismatched after navigating to `/profile` via the navbar.
- [x] **Update navbar "Login" entry** (`convergence_games/app/templates/components/NavBar.html.jinja:92`)
  - Replaced the single `Login → /profile` link (when anonymous) with two entries: `Sign Up → /sign-up` and `Sign In → /sign-in`. Anonymous users hit the right page directly.
- [ ] **Update `before_request_handler`** (`convergence_games/app/routers/frontend/__init__.py:27`)
  - Not required — the existing handler only redirects authenticated-but-unset-up users away from non-`/profile` GETs. New auth paths are anonymous-only, so the handler never affects them. Skipped.
- [x] **Update `OAuthController.get_provider_auth_login`** (`convergence_games/app/routers/frontend/oauth.py:159`)
  - Accept `mode` query parameter; encode into `OAuthRedirectState.mode` for the round-trip.
- [x] **Delete obsolete templates**
  - `pages/register.html.jinja` — gone after `render_profile` is switched.
  - `pages/email_sign_in.html.jinja` — kept (linking flow). Plan revisits removal in Phase 8.

#### Phase 4 verification

- [x] `basedpyright` — clean (only pre-existing `BaseOAuth2` generic warning)
- [x] `ruff check` — clean
- [ ] `npx tsc --noEmit` — clean (in case of any TypeScript that referenced the old paths)
- [x] Manual: load the app unauthenticated, confirm sign-up is the default page, sign-up flow with a brand-new email reaches `VerifyCode`, sign-up flow with an existing email shows `AccountExists`, sign-in flow continues to work (still falls through to legacy auto-create on miss until Phase 5 wires `NoAccountFound`). Also: navigating to `/profile` while anonymous now redirects to `/sign-up` (no mode-mismatch). Bug was `{% set %}` statements above `{% block content %}` in `auth.html.jinja` not running on HTMX block-only renders — fixed by moving them inside the block.

### Phase 5: Post-verification branching for sign-in misses

- [x] **Add `components/NoAccountFound.html.jinja`** + page wrapper `pages/no_account_found.html.jinja`
  - Component takes `email` and `state_token` (encoded `OAuthRedirectState` with `pending_verified_email=email`).
  - Renders "Create a new account" button (`POST /sign-up/from-verified-email` with the token) and OAuth-link buttons that point at `/oauth2/{provider}/login?state=<pending_state_token>` so the verified email survives the round-trip via the existing `extra_email_to_link` plumbing in `authorize_flow`.
  - Page wrapper used because `VerifyCode` form is non-HTMX (full page submit). Same wrapper pattern added for `pages/account_exists.html.jinja`.
- [x] **Update `EmailAuthController.post_verify_code`** (`convergence_games/app/routers/frontend/email_auth.py:101`)
  - Read `mode` from form data; resolve to `AuthIntent`, falling back to `state.mode`.
  - Pass intent to `login_with_email_and_code`.
  - Catch `NoAccountForSignInError`; render `pages/no_account_found.html.jinja` with a freshly issued state token (`OAuthRedirectState(pending_verified_email=email, redirect_path=...)`).
  - Catch `AccountAlreadyExistsError`; render `pages/account_exists.html.jinja`.
- [x] **Update `EmailAuthController.get_magic_link`** similarly
  - Magic links pass `intent=AuthIntent.SIGN_IN` explicitly. Same outcome rendering.
- [x] **Add `POST /sign-up/from-verified-email`** (`convergence_games/app/routers/frontend/profile.py`)
  - Decode the token, re-validate it has `pending_verified_email`, then call `authorize_flow(SIGN_UP, EMAIL, ...)` which creates the user and signs them in.
- [x] **Update `OAuthController.get_provider_auth_login`** (`convergence_games/app/routers/frontend/oauth.py:159`)
  - Accept a raw `state` query parameter; if present, use it verbatim as the OAuth state (lets `NoAccountFound`'s OAuth-link buttons forward the encoded `pending_verified_email` token through Google/Discord).
- [x] **Update `login_with_email_and_code`** (`convergence_games/app/routers/frontend/email_auth.py:28`)
  - Already accepts `intent` (added in Phase 2). The temporary `intent is None` SIGN_UP fallback stays in place to keep the legacy `/email_sign_in` route (still used by the profile-page linking flow with `intent=None`) working until Phase 8 deletes that route.

#### Phase 5 verification

- [x] `basedpyright` — clean (only the pre-existing `BaseOAuth2` generic warning)
- [x] `ruff check` — clean
- [x] Manual: in dev, with no `User` rows, attempt sign-in to a fresh email; verify the code; confirm `NoAccountFound` is rendered. From there, click "Create a new account" → user is created, redirected to profile setup. Repeat: sign-in to a fresh email, verify, click "Sign in with Google" → after Google auth, the new Google user is created with both Google and EMAIL logins.

### Phase 6: OAuth Discord/Facebook link-confirm UI

- [x] **Add `components/LinkOAuthAccount.html.jinja`** + page wrapper `pages/link_oauth_account.html.jinja`
  - Component takes `email`, `provider_label`, `payload_token`. Renders confirm/decline buttons that POST to `/oauth2/link_confirm` with `link=true`/`link=false` and the encoded `PendingOAuthLink` token.
- [x] **Add `OAuthController.post_link_confirm` (`POST /oauth2/link_confirm`)** (`convergence_games/app/routers/frontend/oauth.py`)
  - Decode `PendingOAuthLink` token; if `link=true`, call `authorize_flow(intent=LINK, linking_account_id=candidate_user_id, ...)`; if `link=false`, `authorize_flow(intent=SIGN_UP, ...)` to create a fresh user.
- [x] **Wire Discord/Facebook detection** in `get_provider_auth_authorize` (`convergence_games/app/routers/frontend/oauth.py`)
  - When `find_user_by_email` returns a match and the provider is Discord or Facebook, build a `PendingOAuthLink`, render `pages/link_oauth_account.html.jinja` inline (not a redirect — the OAuth callback is a GET so the response replaces the full page).

#### Phase 6 verification

- [x] `basedpyright` — clean (only pre-existing `BaseOAuth2` generic warning)
- [x] `ruff check` — clean
- [x] Manual: in dev, with an existing email-only account, complete Discord OAuth using a Discord profile whose email matches; confirm `LinkOAuthAccount` is shown; "Link" attaches Discord login to the existing user; "No, create new account" creates a separate user.

### Phase 7: Detection script

- [x] **Add `scripts/find_duplicate_users.py`**
  - Bootstraps async DB session same way as `scripts/create_mock_event.py`.
  - Loads `UserLogin` rows with `User` via selectinload.
  - Groups by `normalize_email(provider_email or provider_user_id)`.
  - Reports cross-user duplicates (same email, different User IDs) and intra-user casing mismatches.
  - `--verbose` flag adds statistics. Exits non-zero if duplicates found.
  - Does not modify data.
- [ ] **Run the script against dev DB**.

#### Phase 7 verification

- [x] `ruff check` — clean
- [x] `basedpyright` — clean (warnings only, no errors)
- [ ] `PYTHONPATH=. uv run python scripts/find_duplicate_users.py` runs without error in dev.

### Phase 8: Cleanup, tests, manual QA

- [ ] **Remove the `/email_sign_in` shim routes** once the new flows are confirmed working (a follow-up commit, not blocking — keep them through one deploy if you want a clean rollout).
- [x] **Add unit tests** under `tests/app/common/test_auth.py`
  - `find_user_by_email`: returns None on miss, matches provider_email, matches EMAIL provider_user_id, case-insensitive, prefers EMAIL-provider user on ambiguity.
  - `authorize_flow(SIGN_UP)`: creates user; raises `AccountAlreadyExistsError` on duplicate.
  - `authorize_flow(SIGN_IN)`: succeeds for existing; raises `NoAccountForSignInError` on miss.
  - `authorize_flow(LINK)`: attaches new login; idempotent for same user; rejects cross-user with 403.
  - Uses SQLite+aiosqlite in-memory DB. Added `pytest-asyncio` and `aiosqlite` dev deps.
- [x] **Add unit tests** under `tests/utils/test_email.py`
  - `normalize_email`: lowercase, strip, combined, already-normalized, empty, whitespace-only.
- [x] **Manual end-to-end run-through**
  1. Sign up fresh email — **pass**.
  2. Sign up existing email — **pass** (renders AccountExists). NOTE: exposes email enumeration; Phase 9 changes to require verify-first.
  3. Sign in known email — **pass**.
  4. Sign in unknown email → NoAccountFound — **pass**.
  5. Create from NoAccountFound — **pass**.
  6. Link via OAuth from NoAccountFound — **pass**.
  7. Google auto-link (Google → existing email) — **pass**.
  8. Google auto-link (email → existing Google) — **pass** but auto-creates instead of prompting. Phase 9 fixes to show NoAccountFound when no Google match (only auto-link when there IS a matching Google account).
  9. Discord cross-provider prompt — **pass**.
  10. Discord decline creates separate — **pass**.
  11. Magic link — **pass**.
  12. Profile linking flow — **pass**.
  13. Nav bar — **pass**.
- [ ] **Issues found in testing (addressed in Phase 9)**
  - Static logos use relative paths (`src="static/icons/..."`) and 404 on `/email_auth/verify_code` because the path resolves relative to the page URL.
  - Linking an already-linked provider returns raw JSON 403 instead of a friendly error page.
  - Sign-up pre-check exposes email enumeration (blocks before code is sent).
  - Email sign-in with unknown email auto-creates when there's no Google auto-link match — should prompt via NoAccountFound instead.

#### Phase 8 verification

- [x] `pytest` — 28 passed
- [x] `basedpyright` — 0 errors (warnings only on argparse Any + test internals)
- [x] `ruff check` — clean
- [ ] `npx tsc --noEmit` — clean

### Phase 9: Fix issues found in manual testing

- [ ] **Fix static logo paths** — `NoAccountFound.html.jinja` and any other templates that inline OAuth button images use `src="static/icons/logos/..."` (relative). On pages under `/email_auth/verify_code`, this resolves to `/email_auth/static/...` and 404s. Change to absolute paths `src="/static/icons/logos/..."` (leading `/`). Audit all templates that reference logo images.
- [ ] **Friendly error for already-linked provider** — When `authorize_flow(LINK)` raises `HTTPException(403, "Another account is already linked...")`, the profile linking flow shows raw JSON. Catch this in `OAuthController.get_provider_auth_authorize` and render a user-friendly error page instead. Could reuse a generic error component or a dedicated `pages/link_error.html.jinja`.
- [ ] **Remove sign-up email enumeration** — Currently `POST /sign-up/email` does a `find_user_by_email` pre-check and blocks before sending a code, revealing whether an email is registered. Change: always send the code (same as sign-in), then catch `AccountAlreadyExistsError` at verify-code time and render `AccountExists`. The pre-check is removed.
- [ ] **Remove email-sign-in auto-create fallback** — The temporary `intent is None → SIGN_UP` fallback in `login_with_email_and_code` causes email sign-in to unknown addresses to auto-create accounts when there's no Google auto-link match. Remove the fallback: when intent is explicitly `SIGN_IN` and no Google match exists, raise `NoAccountForSignInError` so the controller renders `NoAccountFound`. The bridge code marked `TODO(auth-flow-separation)` in `login_with_email_and_code` is the target.

#### Phase 9 verification

- [ ] `basedpyright` — clean
- [ ] `ruff check` — clean
- [ ] Manual: logos render on `/email_auth/verify_code`. Linking already-linked provider shows friendly page. Sign-up with existing email still sends code + blocks at verify. Email sign-in to unknown address prompts NoAccountFound (no auto-create).

## Acceptance Criteria

- [ ] `ruff check` clean
- [ ] `basedpyright` clean
- [ ] `pytest` clean (including new tests for `normalize_email`, `authorize_flow` intents, `find_user_by_email`)
- [ ] `npx tsc --noEmit` clean
- [ ] No call site of `authorize_flow()` lacks an explicit `intent`
- [ ] Sign-up form blocks before sending code when the email already resolves to any user
- [ ] Sign-in form sends a code regardless (no enumeration), and post-verification renders `NoAccountFound` if no user exists
- [ ] Google OAuth silently links a new Google login to an existing email-only user when emails match and `email_verified=True`
- [ ] Discord OAuth surfaces the `LinkOAuthAccount` confirmation screen when emails match
- [ ] All emails are stored lowercased and trimmed — verified by inspecting `UserEmailVerificationCode.email`, `UserLogin.provider_email`, `UserLogin.provider_user_id` (for `EMAIL`) for new rows in dev
- [ ] `scripts/find_duplicate_users.py` runs and reports duplicates without modifying data

## Risks and Mitigations

1. **Race between sign-up pre-check and code-verify create**: a user could pre-check (no account), then a parallel signup completes, then they verify and `authorize_flow(SIGN_UP)` raises `AccountAlreadyExistsError`. Mitigation: catch in the verify-code controller and render `AccountExists` (the user can then sign in).
2. **OAuth provider returns `email_verified=False` or omits the field for Google**: silent linking should not happen. Mitigation: default `ProfileInfo.email_verified=False` and only auto-link when explicitly `True`. Falls through to the sign-up branch otherwise.
3. **Existing duplicate accounts make `find_user_by_email` ambiguous**: with multiple matched users, picking the wrong one for silent linking would attach a Google login to the wrong account. Mitigation: prefer EMAIL-login user, then earliest `created_at`; print a warning when multiple match; surface duplicates via the detection script so operators reconcile before they bite.
4. **Magic link confusion with the new mode-aware flow**: magic links predate the mode field. Mitigation: treat magic links as `SIGN_IN`; `NoAccountForSignInError` from a magic link still lands on `NoAccountFound`, which is the right UX (the user did intend to sign in).
5. **Pending-verified-email token leakage / replay**: token is signed but valid for the cookie session. Mitigation: include the verified email's `UserEmailVerificationCode.id` in the token and consume (delete) the verification code on use; refuse if the code has been consumed or expired. Adds a small DB write but blocks replay.
6. **`before_request_handler` redirect loop**: forgetting to add new auth paths to its allow-list would loop unfinished-profile users. Mitigation: add the new paths in Phase 4 explicitly as a checklist item; manual verify in dev.

## Notes

- A future task should add a uniqueness constraint on `(provider, lower(provider_user_id))` for `UserLogin` plus a partial unique index on `lower(provider_email)` once duplicates are reconciled. Not in scope here because existing dupes would block the migration.
- No data backfill is performed in this task. Existing rows remain in their current casing; only new writes are normalised. The detection script lets operators reassign manually; backfill can be a follow-up after they have done so.
- Discord/Facebook auto-link decision (Q1) trusts the provider only for the *prompt* (not silent link) — actual linking still requires the user to click confirm, so a malicious provider-email assertion cannot silently take over an account.
- Facebook is in the `LoginProvider` enum but no provider client is wired; this plan treats Discord/Facebook the same so when Facebook is wired later it inherits the new behaviour for free.
