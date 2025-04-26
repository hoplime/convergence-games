from __future__ import annotations

import base64
from abc import ABC, abstractmethod
from functools import cached_property
from typing import Annotated, Any, cast

import httpx
import jwt
from httpx_oauth.clients.discord import DiscordOAuth2
from httpx_oauth.clients.google import GoogleOAuth2
from httpx_oauth.oauth2 import BaseOAuth2, OAuth2Token
from litestar import Controller, get, post
from litestar.exceptions import HTTPException
from litestar.params import Parameter
from litestar.response import Redirect
from sqlalchemy.ext.asyncio import AsyncSession

from convergence_games.app.app_config.jwt_cookie_auth import jwt_cookie_auth
from convergence_games.app.common.auth import ProfileInfo, authorize_flow
from convergence_games.app.request_type import Request
from convergence_games.db.models import LoginProvider
from convergence_games.db.ocean import Sqid, sink
from convergence_games.settings import SETTINGS


class OAuthProvider(ABC):
    def __init__(
        self,
        client: BaseOAuth2,
        openid_configuration: str | dict[str, Any],
        verify_kwargs: dict[str, Any] | None = None,
    ):
        self.client = client
        self.openid_configuration = openid_configuration
        self.verify_kwargs = verify_kwargs or {}

    @cached_property
    def openid_data(self) -> dict[str, Any]:
        if isinstance(self.openid_configuration, str):
            response = httpx.get(self.openid_configuration)
            response.raise_for_status()
            self.openid_configuration = cast(dict[str, Any], response.json())
        return self.openid_configuration

    @cached_property
    def jwks_uri(self) -> str:
        return self.openid_data.get("jwks_uri", "")

    @cached_property
    def jwk(self) -> Any:
        response = httpx.get(self.jwks_uri)
        response.raise_for_status()
        return response.json()

    @cached_property
    def algorithms(self) -> list[str]:
        return self.openid_data.get("id_token_signing_alg_values_supported", [])

    @cached_property
    def issuer(self) -> str:
        return self.openid_data.get("issuer", "")

    @abstractmethod
    async def get_profile_info(self, oauth2_token: OAuth2Token) -> ProfileInfo: ...


class GoogleOAuthProvider(OAuthProvider):
    async def get_profile_info(self, oauth2_token: OAuth2Token) -> ProfileInfo:
        id_token = oauth2_token.get("id_token", "")
        access_token = oauth2_token.get("access_token", "")
        jwks_client = jwt.PyJWKClient(self.jwks_uri)
        signing_key = jwks_client.get_signing_key_from_jwt(id_token)
        decoded_token = jwt.decode_complete(
            id_token,
            key=signing_key,
            algorithms=self.algorithms,
            **self.verify_kwargs,
        )
        payload, header = cast(dict[str, Any], decoded_token["payload"]), decoded_token["header"]
        alg_obj = jwt.get_algorithm_by_name(header["alg"])
        digest = alg_obj.compute_hash_digest(bytes(access_token, encoding="utf-8"))
        at_hash = base64.urlsafe_b64encode(digest[: (len(digest) // 2)]).rstrip(b"=")
        if at_hash != bytes(cast(str, payload.get("at_hash")), encoding="utf-8"):
            raise ValueError("Invalid access token hash")
        return ProfileInfo(
            user_first_name=payload.get("given_name"),
            user_last_name=payload.get("family_name"),
            user_id=payload.get("sub"),
            user_email=payload.get("email"),
            user_profile_picture=payload.get("picture"),
        )


class DiscordOAuthProvider(OAuthProvider):
    async def get_profile_info(self, oauth2_token: OAuth2Token) -> ProfileInfo:
        access_token = oauth2_token.get("access_token", "")
        async with self.client.get_httpx_client() as client:
            response = await client.get(
                "https://discord.com/api/users/@me",
                headers={**self.client.request_headers, "Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            data = cast(dict[str, Any], response.json())
            return ProfileInfo(
                user_id=data.get("id"),
                user_email=data.get("email"),
                user_profile_picture=f"https://cdn.discordapp.com/avatars/{data.get('id')}/{data.get('avatar')}.png",
            )


GOOGLE_PROVIDER = GoogleOAuthProvider(
    client=GoogleOAuth2(
        client_id=SETTINGS.GOOGLE_CLIENT_ID,
        client_secret=SETTINGS.GOOGLE_CLIENT_SECRET,
        scopes=["openid", "email", "profile"],
    ),
    openid_configuration="https://accounts.google.com/.well-known/openid-configuration",
    verify_kwargs={
        "audience": SETTINGS.GOOGLE_CLIENT_ID,
    },
)
DISCORD_PROVIDER = DiscordOAuthProvider(
    client=DiscordOAuth2(
        client_id=SETTINGS.DISCORD_CLIENT_ID,
        client_secret=SETTINGS.DISCORD_CLIENT_SECRET,
        scopes=["identify", "email"],
    ),
    openid_configuration="https://discord.com/.well-known/openid-configuration",
    verify_kwargs={
        "audience": SETTINGS.DISCORD_CLIENT_ID,
    },
)

OAUTH_PROVIDERS = {LoginProvider.GOOGLE: GOOGLE_PROVIDER, LoginProvider.DISCORD: DISCORD_PROVIDER}


def get_oauth_provider(provider_name: LoginProvider) -> OAuthProvider:
    provider_client = OAUTH_PROVIDERS.get(provider_name)
    if provider_client is None:
        raise HTTPException(detail="Provider not found", status_code=404)
    return provider_client


def build_redirect_uri(provider_name: LoginProvider) -> str:
    return f"{SETTINGS.BASE_REDIRECT_URI}/oauth2/{provider_name}/authorize"


class OAuthController(Controller):
    path = "/oauth2"

    @post(path="/logout")
    async def post_logout(self, redirect_path: str = "/profile") -> Redirect:
        token_key = jwt_cookie_auth.key
        response = Redirect(path=redirect_path)
        response.delete_cookie(token_key)
        return response

    @get(path="/{provider_name:str}/login")
    async def get_provider_auth_login(
        self,
        provider_name: LoginProvider,
        request: Request,
        linking_account_sqid: Sqid | None = None,
    ) -> Redirect:
        linking_account_id = sink(linking_account_sqid) if linking_account_sqid is not None else None
        if linking_account_id is not None and (request.user is None or linking_account_id != request.user.id):
            raise HTTPException(detail="Invalid linking account ID", status_code=403)

        provider = get_oauth_provider(provider_name)
        redirect_uri = build_redirect_uri(provider_name)

        auth_url = await provider.client.get_authorization_url(redirect_uri=redirect_uri, state=linking_account_sqid)
        return Redirect(path=auth_url)

    @get(path="/{provider_name:str}/authorize")
    async def get_provider_auth_authorize(
        self,
        code: str,
        provider_name: LoginProvider,
        transaction: AsyncSession,
        state_query: Annotated[str | None, Parameter(query="state")] = None,
    ) -> Redirect:
        # TODO: Better state handling with a signing key - not just using it to encode the SQID
        linking_account_sqid = cast(Sqid, state_query) if state_query is not None else None
        linking_account_id = sink(linking_account_sqid) if linking_account_sqid is not None else None
        provider = get_oauth_provider(provider_name)
        redirect_uri = build_redirect_uri(provider_name)

        oauth2_token = await provider.client.get_access_token(code=code, redirect_uri=redirect_uri)
        profile_info = await provider.get_profile_info(oauth2_token)

        return await authorize_flow(
            transaction=transaction,
            provider_name=provider_name,
            profile_info=profile_info,
            linking_account_id=linking_account_id,
        )
