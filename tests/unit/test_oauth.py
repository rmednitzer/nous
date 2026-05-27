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


def test_single_client_replaces_on_re_dcr(provider: FileOAuthProvider) -> None:
    asyncio.run(provider.register_client(_client("c-1")))
    asyncio.run(provider.register_client(_client("c-2")))
    assert asyncio.run(provider.get_client("c-1")) is None
    fetched = asyncio.run(provider.get_client("c-2"))
    assert fetched is not None
    assert fetched.client_id == "c-2"


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


# --- AUDIT-2026-05-20 H6: file-store hardening (lock + chmod + fsync) ---


def test_save_tightens_mode_to_0600(provider: FileOAuthProvider, tmp_path: Path) -> None:
    """H6: every state file ends ``0o600`` so a sibling process cannot read it."""
    asyncio.run(provider.register_client(_client()))
    provider._issue("c-1", ["mcp:tools"])

    for name in ("clients.json", "tokens.json"):
        path = tmp_path / "auth" / name
        assert path.exists(), name
        mode = path.stat().st_mode & 0o777
        assert mode == 0o600, f"{name} mode is {oct(mode)}; want 0o600"


def test_concurrent_register_clients_preserves_every_record(tmp_path: Path) -> None:
    """H6: load+save under the provider lock; concurrent writes do not clobber.

    Without the lock, three parallel ``register_client`` calls would
    race on ``load() ... save()`` and the last writer would overwrite
    the others. The provider-level ``asyncio.Lock`` serialises the
    sequence so every registration persists.
    """
    p = FileOAuthProvider(
        tmp_path / "auth",
        single_client=False,
        access_ttl=3600,
        refresh_ttl=86_400,
        code_ttl=60,
    )

    async def _run() -> None:
        await asyncio.gather(
            p.register_client(_client("c-1")),
            p.register_client(_client("c-2")),
            p.register_client(_client("c-3")),
        )

    asyncio.run(_run())

    for cid in ("c-1", "c-2", "c-3"):
        assert asyncio.run(p.get_client(cid)) is not None, cid


# --- AUDIT-2026-05-20 H7: refresh-token family revocation ---


def test_issued_tokens_share_an_issue_id(provider: FileOAuthProvider) -> None:
    """H7 (foundation): a single ``_issue`` call writes both records with
    the same ``issue_id``. Family revocation depends on this invariant."""
    pair = provider._issue("c-1", ["mcp:tools"])

    tokens = provider._tokens.load()
    access_rec = tokens[pair.access_token]
    refresh_rec = tokens["refresh:" + (pair.refresh_token or "")]
    assert access_rec["issue_id"]
    assert access_rec["issue_id"] == refresh_rec["issue_id"]


def test_rotation_propagates_issue_id(provider: FileOAuthProvider) -> None:
    """H7: a rotation must preserve the family identifier so the family
    stays revocable as a unit."""
    pair_1 = provider._issue("c-1", ["mcp:tools"])
    refresh_1 = asyncio.run(
        provider.load_refresh_token(_client(), pair_1.refresh_token or "")
    )
    assert refresh_1 is not None

    pair_2 = asyncio.run(
        provider.exchange_refresh_token(_client(), refresh_1, ["mcp:tools"])
    )

    tokens = provider._tokens.load()
    original_issue = tokens["refresh:" + (pair_1.refresh_token or "")]["issue_id"]
    rotated_issue = tokens["refresh:" + (pair_2.refresh_token or "")]["issue_id"]
    assert rotated_issue == original_issue


def test_refresh_token_reuse_revokes_entire_family(
    provider: FileOAuthProvider,
) -> None:
    """H7: presenting a consumed refresh token revokes every active
    record sharing its ``issue_id`` per OAuth 2.1 BCP §4.13."""
    pair_1 = provider._issue("c-1", ["mcp:tools"])
    refresh_1 = asyncio.run(
        provider.load_refresh_token(_client(), pair_1.refresh_token or "")
    )
    assert refresh_1 is not None
    pair_2 = asyncio.run(
        provider.exchange_refresh_token(_client(), refresh_1, ["mcp:tools"])
    )
    # The rotated pair works before the reuse.
    assert (
        asyncio.run(provider.load_access_token(pair_2.access_token)) is not None
    )

    # Reuse the consumed refresh token. ``load_refresh_token`` returns
    # ``None`` and fires family revocation as a side effect.
    reused = asyncio.run(
        provider.load_refresh_token(_client(), pair_1.refresh_token or "")
    )
    assert reused is None

    # The rotated access token is now revoked.
    assert asyncio.run(provider.load_access_token(pair_2.access_token)) is None


def test_exchange_reuse_also_revokes_family(provider: FileOAuthProvider) -> None:
    """H7: ``exchange_refresh_token`` itself must defend against reuse
    even when ``load_refresh_token`` was skipped. Raises
    ``ValueError`` and revokes the family."""
    pair_1 = provider._issue("c-1", ["mcp:tools"])
    refresh_1 = asyncio.run(
        provider.load_refresh_token(_client(), pair_1.refresh_token or "")
    )
    assert refresh_1 is not None
    pair_2 = asyncio.run(
        provider.exchange_refresh_token(_client(), refresh_1, ["mcp:tools"])
    )

    # Reuse pair_1 directly through exchange without going through load.
    with pytest.raises(ValueError, match="reuse"):
        asyncio.run(
            provider.exchange_refresh_token(_client(), refresh_1, ["mcp:tools"])
        )

    # Rotated pair is revoked.
    assert asyncio.run(provider.load_access_token(pair_2.access_token)) is None
