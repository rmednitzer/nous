"""Tests for the file-backed OAuth 2.1 provider."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from mcp.server.auth.provider import AuthorizationCode
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyHttpUrl

from nous.auth import FileOAuthProvider, build_auth_settings, make_oauth_provider
from nous.config import Settings


def _client(client_id: str = "c-1") -> OAuthClientInformationFull:
    return OAuthClientInformationFull(
        client_id=client_id,
        client_secret="s",
        redirect_uris=[AnyHttpUrl("https://example.com/cb")],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        scope="mcp:tools",
    )


@pytest.fixture
def provider(tmp_path: Path) -> FileOAuthProvider:
    return FileOAuthProvider(
        tmp_path / "auth",
        single_client=True,
        access_ttl=3600,
        refresh_ttl=86_400,
        code_ttl=60,
    )


def test_build_auth_settings_uses_issuer() -> None:
    s = build_auth_settings("https://nous.example.org")
    assert str(s.issuer_url).rstrip("/") == "https://nous.example.org"
    assert "mcp:tools" in s.required_scopes
    assert s.client_registration_options is not None
    assert s.client_registration_options.enabled is True


def test_make_oauth_provider_from_settings(tmp_path: Path) -> None:
    settings = Settings(home=tmp_path)
    p = make_oauth_provider(settings)
    assert isinstance(p, FileOAuthProvider)


def test_register_then_get_client(provider: FileOAuthProvider) -> None:
    asyncio.run(provider.register_client(_client()))
    fetched = asyncio.run(provider.get_client("c-1"))
    assert fetched is not None
    assert fetched.client_id == "c-1"


def test_single_client_lockdown(provider: FileOAuthProvider) -> None:
    asyncio.run(provider.register_client(_client("c-1")))
    with pytest.raises(ValueError, match="single-client lockdown"):
        asyncio.run(provider.register_client(_client("c-2")))


def test_issue_then_load_access_token(provider: FileOAuthProvider) -> None:
    token = provider._issue("c-1", ["mcp:tools"])
    loaded = asyncio.run(provider.load_access_token(token.access_token))
    assert loaded is not None
    assert loaded.client_id == "c-1"
    assert "mcp:tools" in loaded.scopes


def test_unknown_access_token_returns_none(provider: FileOAuthProvider) -> None:
    assert asyncio.run(provider.load_access_token("nope")) is None


def test_revoke_clears_access_and_refresh(provider: FileOAuthProvider) -> None:
    token = provider._issue("c-1", ["mcp:tools"])
    access = asyncio.run(provider.load_access_token(token.access_token))
    assert access is not None
    asyncio.run(provider.revoke_token(access))
    assert asyncio.run(provider.load_access_token(token.access_token)) is None


def test_refresh_rotates_token(provider: FileOAuthProvider) -> None:
    token = provider._issue("c-1", ["mcp:tools"])
    refresh = asyncio.run(provider.load_refresh_token(_client(), token.refresh_token))
    assert refresh is not None
    new_token = asyncio.run(
        provider.exchange_refresh_token(_client(), refresh, ["mcp:tools"])
    )
    assert new_token.access_token != token.access_token
    assert new_token.refresh_token != token.refresh_token
    # The old refresh token must not work twice.
    assert (
        asyncio.run(provider.load_refresh_token(_client(), token.refresh_token))
        is None
    )


def test_exchange_authorization_code_consumes_it(provider: FileOAuthProvider) -> None:
    code = AuthorizationCode(
        code="c-code",
        scopes=["mcp:tools"],
        expires_at=float(2 << 30),
        client_id="c-1",
        code_challenge="",
        redirect_uri=AnyHttpUrl("https://example.com/cb"),
        redirect_uri_provided_explicitly=True,
    )
    # Seed the store directly so exchange has something to remove.
    provider._codes.save({code.code: {"client_id": "c-1"}})
    token = asyncio.run(provider.exchange_authorization_code(_client(), code))
    assert token.access_token
    # Code is consumed.
    assert asyncio.run(provider.load_authorization_code(_client(), code.code)) is None
