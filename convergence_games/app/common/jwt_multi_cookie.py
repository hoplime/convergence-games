"""Generic multi-cookie JWT auth for Litestar.

Provides JWTMultiCookieAuth (access + refresh + legacy cookie support) and
JWTMultiCookieAuthenticationMiddleware, following Litestar's JWTCookieAuth
patterns. Application-specific logic (DB sessions, rotation, etc.) is
injected via RefreshTokenHandler callbacks.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from litestar.connection import ASGIConnection
from litestar.datastructures import Cookie
from litestar.exceptions import NotAuthorizedException
from litestar.middleware.authentication import AuthenticationResult
from litestar.middleware.base import DefineMiddleware
from litestar.openapi.spec import Components, SecurityScheme
from litestar.response import Response
from litestar.security.jwt import JWTCookieAuth, JWTCookieAuthenticationMiddleware, Token
from litestar.status_codes import HTTP_201_CREATED
from litestar.types import Method, Receive, Scope, Scopes, Send
from litestar.types.empty import Empty

type SameSite = Literal["lax", "strict", "none"]
type RefreshTokenHandler = Callable[[Token, ASGIConnection[Any, Any, Any, Any]], Awaitable[RefreshResult | None]]


@dataclass
class RefreshResult:
    """Returned by refresh/legacy handlers to the middleware."""

    user: Any
    token_extras: dict[str, Any]
    cookies: list[Cookie] = field(default_factory=list)
    session_jti: str | None = None


# --- Middleware (defined before the auth config so the config can reference it) ---


class JWTMultiCookieAuthenticationMiddleware(JWTCookieAuthenticationMiddleware):
    """Authenticates via access cookie, falling back to refresh-cookie rotation or
    legacy single-token migration. Unauthenticated requests degrade to anonymous."""

    __slots__ = (
        "access_token_expiration",
        "cookie_domain",
        "cookie_path",
        "cookie_samesite",
        "cookie_secure",
        "legacy_cookie_key",
        "legacy_handler",
        "refresh_cookie_key",
        "refresh_handler",
        "rotation_grace_seconds",
    )

    def __init__(
        self,
        algorithm: str,
        app: Any,
        auth_cookie_key: str,
        auth_header: str,
        exclude: str | list[str] | None,
        exclude_opt_key: str,
        exclude_http_methods: Sequence[Method] | None,
        retrieve_user_handler: Callable[..., Awaitable[Any]],
        scopes: Scopes,
        token_secret: str,
        token_cls: type[Token] = Token,
        token_audience: Sequence[str] | None = None,
        token_issuer: Sequence[str] | None = None,
        require_claims: Sequence[str] | None = None,
        verify_expiry: bool = True,
        verify_not_before: bool = True,
        strict_audience: bool = False,
        revoked_token_handler: Callable[..., Awaitable[Any]] | None = None,
        # Multi-cookie params
        refresh_cookie_key: str = "refresh",
        legacy_cookie_key: str = "token",
        refresh_handler: RefreshTokenHandler | None = None,
        legacy_handler: RefreshTokenHandler | None = None,
        rotation_grace_seconds: int = 5,
        access_token_expiration: timedelta | None = None,
        cookie_path: str = "/",
        cookie_secure: bool | None = None,
        cookie_samesite: SameSite = "lax",
        cookie_domain: str | None = None,
    ) -> None:
        super().__init__(
            algorithm=algorithm,
            app=app,
            auth_cookie_key=auth_cookie_key,
            auth_header=auth_header,
            exclude=exclude,
            exclude_opt_key=exclude_opt_key,
            exclude_http_methods=exclude_http_methods,
            retrieve_user_handler=retrieve_user_handler,
            scopes=scopes,
            token_secret=token_secret,
            token_cls=token_cls,
            token_audience=token_audience,
            token_issuer=token_issuer,
            require_claims=require_claims,
            verify_expiry=verify_expiry,
            verify_not_before=verify_not_before,
            strict_audience=strict_audience,
            revoked_token_handler=revoked_token_handler,
        )
        self.refresh_cookie_key = refresh_cookie_key
        self.legacy_cookie_key = legacy_cookie_key
        self.refresh_handler = refresh_handler
        self.legacy_handler = legacy_handler
        self.rotation_grace_seconds = rotation_grace_seconds
        self.access_token_expiration = access_token_expiration or timedelta(minutes=15)
        self.cookie_path = cookie_path
        self.cookie_secure = cookie_secure
        self.cookie_samesite = cookie_samesite
        self.cookie_domain = cookie_domain

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        state = scope.setdefault("state", {})  # pyright: ignore[reportArgumentType]
        state.setdefault("pending_auth_cookies", [])
        state.setdefault("current_session_jti", None)

        async def wrapped_send(message: Any) -> None:
            if message["type"] == "http.response.start":
                pending: list[Cookie] = state.get("pending_auth_cookies", [])
                if pending:
                    headers = list(message.get("headers", []) or [])
                    for cookie in pending:
                        headers.append(cookie.to_encoded_header())
                    message = {**message, "headers": headers}
            await send(message)

        await super().__call__(scope, receive, wrapped_send)

    async def authenticate_request(self, connection: ASGIConnection[Any, Any, Any, Any]) -> AuthenticationResult:
        try:
            return await self._authenticate(connection)
        except NotAuthorizedException:
            return AuthenticationResult(user=None, auth=None)

    async def _authenticate(  # noqa: C901
        self, connection: ASGIConnection[Any, Any, Any, Any]
    ) -> AuthenticationResult:
        cookies = connection.cookies

        # Phase 1: Access cookie (hot path — pure JWT decode, no DB).
        access_value = cookies.get(self.auth_cookie_key)
        if access_value:
            try:
                token = self._decode(access_value)
                token_type = getattr(token, "token_type", None) or token.extras.get("token_type")
                if token_type == "access":
                    user = await self.retrieve_user_handler(token, connection)
                    if user is not None:
                        return AuthenticationResult(user=user, auth=token)
            except (NotAuthorizedException, Exception):
                pass

        # Phase 2: Refresh cookie.
        refresh_value = cookies.get(self.refresh_cookie_key)
        if refresh_value and self.refresh_handler is not None:
            try:
                result = await self._handle_token_with_handler(
                    connection, refresh_value, self.refresh_handler, clear_cookie_key=None
                )
                if result is not None:
                    return result
            except NotAuthorizedException:
                pass

        # Phase 3: Legacy cookie.
        legacy_value = cookies.get(self.legacy_cookie_key)
        if legacy_value and self.legacy_handler is not None:
            try:
                result = await self._handle_token_with_handler(
                    connection, legacy_value, self.legacy_handler, clear_cookie_key=self.legacy_cookie_key
                )
                if result is not None:
                    return result
            except NotAuthorizedException:
                self._queue_cookie(connection.scope, self._make_clear_cookie(self.legacy_cookie_key))

        return AuthenticationResult(user=None, auth=None)

    async def _handle_token_with_handler(
        self,
        connection: ASGIConnection[Any, Any, Any, Any],
        encoded: str,
        handler: RefreshTokenHandler,
        *,
        clear_cookie_key: str | None,
    ) -> AuthenticationResult | None:
        token = self._decode(encoded)
        refresh_result = await handler(token, connection)
        if refresh_result is None:
            return None

        extras = {**refresh_result.token_extras, "token_type": "access"}
        access_token = self.token_cls(
            sub=token.sub,
            exp=datetime.now(timezone.utc) + self.access_token_expiration,
            extras=extras,
        )
        encoded_access = access_token.encode(secret=self.token_secret, algorithm=self.algorithm)
        self._queue_cookie(
            connection.scope,
            Cookie(
                key=self.auth_cookie_key,
                value=encoded_access,
                path=self.cookie_path,
                httponly=True,
                secure=self.cookie_secure,
                samesite=self.cookie_samesite,  # pyright: ignore[reportArgumentType]
                domain=self.cookie_domain,
                max_age=int(self.access_token_expiration.total_seconds()),
            ),
        )

        for cookie in refresh_result.cookies:
            self._queue_cookie(connection.scope, cookie)

        if clear_cookie_key is not None:
            self._queue_cookie(connection.scope, self._make_clear_cookie(clear_cookie_key))

        if refresh_result.session_jti is not None:
            state = connection.scope.setdefault("state", {})  # pyright: ignore[reportArgumentType]
            state["current_session_jti"] = refresh_result.session_jti

        return AuthenticationResult(user=refresh_result.user, auth=token)

    def _decode(self, encoded: str) -> Token:
        return self.token_cls.decode(
            encoded_token=encoded,
            secret=self.token_secret,
            algorithm=self.algorithm,
        )

    def _queue_cookie(self, scope: Scope, cookie: Cookie) -> None:
        state = scope.setdefault("state", {})  # pyright: ignore[reportArgumentType]
        state.setdefault("pending_auth_cookies", []).append(cookie)

    def _make_clear_cookie(self, key: str) -> Cookie:
        return Cookie(
            key=key,
            value="",
            path=self.cookie_path,
            httponly=True,
            secure=self.cookie_secure,
            samesite=self.cookie_samesite,  # pyright: ignore[reportArgumentType]
            domain=self.cookie_domain,
            max_age=0,
        )


# --- Auth config ---


@dataclass
class JWTMultiCookieAuth(JWTCookieAuth[Any, Token]):
    """JWT authentication config that emits access + refresh + legacy-clear cookies."""

    refresh_key: str = field(default="refresh")
    legacy_key: str = field(default="token")
    refresh_token_expiration: timedelta = field(default_factory=lambda: timedelta(days=180))
    rotation_grace_seconds: int = field(default=5)
    refresh_handler: RefreshTokenHandler | None = field(default=None)
    legacy_handler: RefreshTokenHandler | None = field(default=None)
    authentication_middleware_class: type[JWTMultiCookieAuthenticationMiddleware] = field(  # pyright: ignore[reportIncompatibleVariableOverride]
        default=JWTMultiCookieAuthenticationMiddleware
    )

    def _make_cookie(self, key: str, value: str, max_age: int) -> Cookie:
        return Cookie(
            key=key,
            value=value,
            path=self.path,
            httponly=True,
            secure=self.secure,
            samesite=self.samesite,
            domain=self.domain,
            max_age=max_age,
        )

    def create_login_cookies(
        self,
        identifier: str,
        *,
        token_extras: dict[str, Any] | None = None,
        token_expiration: timedelta | None = None,
        refresh_token_unique_jwt_id: str | None = None,
        refresh_token_expiration: timedelta | None = None,
    ) -> list[Cookie]:
        """Create access + refresh + legacy-clear cookies for a login."""
        access_ttl = token_expiration or self.default_token_expiration
        refresh_ttl = refresh_token_expiration or self.refresh_token_expiration
        jti = refresh_token_unique_jwt_id or uuid.uuid4().hex

        access_extras = {**(token_extras or {}), "token_type": "access"}
        access_encoded = self.create_token(
            identifier=identifier, token_expiration=access_ttl, token_extras=access_extras
        )
        refresh_encoded = self.create_token(
            identifier=identifier,
            token_expiration=refresh_ttl,
            token_unique_jwt_id=jti,
            token_extras={"token_type": "refresh"},
        )
        return [
            self._make_cookie(self.key, access_encoded, int(access_ttl.total_seconds())),
            self._make_cookie(self.refresh_key, refresh_encoded, int(refresh_ttl.total_seconds())),
            self._make_cookie(self.legacy_key, "", 0),
        ]

    def create_refresh_cookie(
        self,
        identifier: str,
        jti: str,
        refresh_token_expiration: timedelta | None = None,
    ) -> Cookie:
        """Create a single refresh cookie (used by handlers during rotation)."""
        ttl = refresh_token_expiration or self.refresh_token_expiration
        encoded = self.create_token(
            identifier=identifier,
            token_expiration=ttl,
            token_unique_jwt_id=jti,
            token_extras={"token_type": "refresh"},
        )
        return self._make_cookie(self.refresh_key, encoded, int(ttl.total_seconds()))

    def delete_cookies_from_response(self, response: Response[Any]) -> None:
        """Delete all auth cookies (access, refresh, legacy) from a response."""
        for key in (self.key, self.refresh_key, self.legacy_key):
            response.delete_cookie(key)

    def login(
        self,
        identifier: str,
        *,
        response_body: Any = Empty,
        response_media_type: str = "application/json",
        response_status_code: int = HTTP_201_CREATED,
        token_expiration: timedelta | None = None,
        token_issuer: str | None = None,
        token_audience: str | None = None,
        token_unique_jwt_id: str | None = None,
        token_extras: dict[str, Any] | None = None,
        send_token_as_response_body: bool = False,
        refresh_token_unique_jwt_id: str | None = None,
        refresh_token_expiration: timedelta | None = None,
    ) -> Response[Any]:
        """Create a response with access + refresh + legacy-clear cookies."""
        cookies = self.create_login_cookies(
            identifier=identifier,
            token_extras=token_extras,
            token_expiration=token_expiration,
            refresh_token_unique_jwt_id=refresh_token_unique_jwt_id,
            refresh_token_expiration=refresh_token_expiration,
        )
        access_encoded = self.create_token(
            identifier=identifier,
            token_expiration=token_expiration,
            token_issuer=token_issuer,
            token_audience=token_audience,
            token_unique_jwt_id=token_unique_jwt_id,
            token_extras=token_extras,
        )
        if response_body is not Empty:
            body = response_body
        elif send_token_as_response_body:
            body = {"token": access_encoded}
        else:
            body = None

        return self.create_response(
            content=body,
            headers={self.auth_header: self.format_auth_header(access_encoded)},
            cookies=cookies,
            media_type=response_media_type,
            status_code=response_status_code,
        )

    @property
    def openapi_components(self) -> Components:
        return Components(
            security_schemes={
                self.openapi_security_scheme_name: SecurityScheme(
                    type="http",
                    scheme="Bearer",
                    name=self.key,
                    security_scheme_in="cookie",
                    bearer_format="JWT",
                    description=self.description,
                )
            }
        )

    @property
    def middleware(self) -> DefineMiddleware:
        return DefineMiddleware(
            self.authentication_middleware_class,
            algorithm=self.algorithm,
            auth_cookie_key=self.key,
            auth_header=self.auth_header,
            exclude=self.exclude,
            exclude_opt_key=self.exclude_opt_key,
            exclude_http_methods=self.exclude_http_methods,
            retrieve_user_handler=self.retrieve_user_handler,
            revoked_token_handler=self.revoked_token_handler,
            scopes=self.scopes,
            token_secret=self.token_secret,
            token_cls=self.token_cls,
            token_issuer=self.accepted_issuers,
            token_audience=self.accepted_audiences,
            require_claims=self.require_claims,
            verify_expiry=self.verify_expiry,
            verify_not_before=self.verify_not_before,
            strict_audience=self.strict_audience,
            refresh_cookie_key=self.refresh_key,
            legacy_cookie_key=self.legacy_key,
            refresh_handler=self.refresh_handler,
            legacy_handler=self.legacy_handler,
            rotation_grace_seconds=self.rotation_grace_seconds,
            access_token_expiration=self.default_token_expiration,
            cookie_path=self.path,
            cookie_secure=self.secure,
            cookie_samesite=self.samesite,
            cookie_domain=self.domain,
        )
