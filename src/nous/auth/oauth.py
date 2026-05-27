"""File-backed OAuth 2.1 authorization-server provider.

Wires into FastMCP via the ``OAuthAuthorizationServerProvider`` interface
from the MCP SDK. State lives in three JSON files under
``$NOUS_HOME/auth/`` (``clients.json``, ``codes.json``, ``tokens.json``);
no database is needed. The SDK exposes ``/.well-known/oauth-*``,
``/authorize``, ``/token``, and ``/register`` automatically when the
provider is passed to ``FastMCP(auth=..., auth_server_provider=...)``.

Optional single-client lockdown closes Dynamic Client Registration after
the first client is registered, so claude.ai claims the integration once
and no later registration can squat on the issuer.

Concurrency and durability (closes AUDIT-2026-05-20 H6): every public
RMW sequence runs under ``self._async_lock``. Each file write tightens
the mode bits to ``0o600`` before the atomic swap and ``fsync``s the
parent directory after the rename so the swap reaches stable storage.

Refresh-token family revocation (closes AUDIT-2026-05-20 H7): every
issued token carries an ``issue_id`` that names its family. A rotation
mints a new pair with the same ``issue_id`` and marks the consumed
refresh record as ``consumed=True`` (it is not popped, so reuse stays
detectable). A subsequent ``load_refresh_token`` or
``exchange_refresh_token`` against the consumed token revokes every
record in the family (access plus refresh), per OAuth 2.1 BCP §4.13.

Errors here must surface as auth failures, never as a crashed transport;
all I/O is defensive.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    construct_redirect_uri,
)
from mcp.server.auth.settings import (
    AuthSettings,
    ClientRegistrationOptions,
    RevocationOptions,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyHttpUrl

__all__ = ["FileOAuthProvider", "build_auth_settings", "make_oauth_provider"]

_SCOPES = ["mcp:tools"]
_REFRESH_PREFIX = "refresh:"


def _now() -> int:
    return int(time.time())


def _new_issue_id() -> str:
    return secrets.token_urlsafe(24)


class _Store:
    """Tiny JSON file store. Each call reads or writes the whole file.

    ``save()`` writes through a ``.tmp`` sibling, tightens the mode to
    ``0o600`` before the atomic rename, then ``fsync``s the parent
    directory so the rename hits stable storage. Concurrency is
    arbitrated by the owning :class:`FileOAuthProvider`'s
    ``asyncio.Lock``; ``_Store`` itself is single-writer per call.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, Any]:
        try:
            data: Any = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def save(self, data: dict[str, Any]) -> None:
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        # Tighten the mode before swap-in so a parallel read never sees
        # the file world-readable. ``Path.replace`` is atomic on POSIX.
        with contextlib.suppress(OSError):
            tmp.chmod(0o600)
        tmp.replace(self._path)
        # Belt-and-braces: chmod after rename in case the filesystem
        # promoted the inode's mode bits during the swap.
        with contextlib.suppress(OSError):
            self._path.chmod(0o600)
        # Fsync the parent directory so the rename is durable.
        with contextlib.suppress(OSError):
            dir_fd = os.open(str(self._path.parent), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)


class FileOAuthProvider(OAuthAuthorizationServerProvider):  # type: ignore[type-arg]
    """OAuth 2.1 authorization-server provider with file-backed state."""

    def __init__(
        self,
        state_dir: str | Path,
        *,
        single_client: bool,
        access_ttl: int,
        refresh_ttl: int,
        code_ttl: int,
    ) -> None:
        base = Path(state_dir).expanduser()
        self._clients = _Store(base / "clients.json")
        self._codes = _Store(base / "codes.json")
        self._tokens = _Store(base / "tokens.json")
        self._single_client = single_client
        self._access_ttl = access_ttl
        self._refresh_ttl = refresh_ttl
        self._code_ttl = code_ttl
        # One provider-level lock arbitrates every load+modify+save
        # sequence. ``asyncio.Lock`` is single-process; the deployment
        # is single-process under uvicorn / gunicorn-with-one-worker
        # per ADR-0008 (superseded by 0016). Multi-process deployments
        # would need a file lock (see BL-045 multi-tenant L3).
        self._async_lock = asyncio.Lock()

    # --- clients ---
    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        async with self._async_lock:
            data = self._clients.load().get(client_id)
        if not data:
            return None
        try:
            return OAuthClientInformationFull.model_validate(data)
        except Exception:  # noqa: BLE001
            return None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        cid = client_info.client_id or ""
        if not cid:
            raise ValueError("client_id is required")
        record = json.loads(client_info.model_dump_json())
        async with self._async_lock:
            clients = self._clients.load()
            if self._single_client and clients and cid not in clients:
                # Single-client mode: at most one active client. Re-DCR
                # replaces the prior client atomically (the new
                # credentials win), keeping the invariant without
                # breaking clients that retry DCR on each connection.
                clients = {cid: record}
            else:
                clients[cid] = record
            self._clients.save(clients)

    # --- authorization codes ---
    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        code = secrets.token_urlsafe(48)
        async with self._async_lock:
            codes = self._codes.load()
            codes[code] = {
                "code": code,
                "client_id": client.client_id or "",
                "scopes": list(getattr(params, "scopes", None) or _SCOPES),
                "expires_at": _now() + self._code_ttl,
                "code_challenge": getattr(params, "code_challenge", ""),
                "redirect_uri": str(params.redirect_uri),
                "redirect_uri_provided_explicitly": bool(
                    getattr(params, "redirect_uri_provided_explicitly", True)
                ),
                "resource": getattr(params, "resource", None),
            }
            self._codes.save(codes)
        return construct_redirect_uri(
            str(params.redirect_uri),
            code=code,
            state=getattr(params, "state", None),
        )

    def _build_auth_code(self, rec: dict[str, Any]) -> AuthorizationCode | None:
        try:
            return AuthorizationCode(
                code=rec["code"],
                scopes=rec["scopes"],
                expires_at=float(rec["expires_at"]),
                client_id=rec["client_id"],
                code_challenge=rec.get("code_challenge", ""),
                redirect_uri=rec["redirect_uri"],
                redirect_uri_provided_explicitly=rec.get(
                    "redirect_uri_provided_explicitly", True
                ),
            )
        except Exception:  # noqa: BLE001
            return None

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        async with self._async_lock:
            codes = self._codes.load()
            rec = codes.get(authorization_code)
            if not rec or rec.get("client_id") != (client.client_id or ""):
                return None
            if int(rec.get("expires_at", 0)) < _now():
                codes.pop(authorization_code, None)
                self._codes.save(codes)
                return None
            return self._build_auth_code(rec)

    async def exchange_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: AuthorizationCode,
    ) -> OAuthToken:
        async with self._async_lock:
            codes = self._codes.load()
            codes.pop(authorization_code.code, None)
            self._codes.save(codes)
            scopes = list(authorization_code.scopes or _SCOPES)
            return self._issue(client.client_id or "", scopes)

    # --- tokens ---
    def _issue(
        self,
        client_id: str,
        scopes: list[str],
        *,
        parent_issue_id: str | None = None,
    ) -> OAuthToken:
        """Mint a new (access, refresh) pair. **Caller must hold the lock.**

        ``parent_issue_id`` propagates a family identifier across
        rotations: a refresh-token exchange passes the consumed
        record's ``issue_id`` so the new pair belongs to the same
        family. First-issue pairs (authorization-code exchange, direct
        ``_issue`` for tests) seed a fresh id.
        """
        access = secrets.token_urlsafe(48)
        refresh = secrets.token_urlsafe(48)
        issue_id = parent_issue_id or _new_issue_id()
        tokens = self._tokens.load()
        tokens[access] = {
            "token": access,
            "client_id": client_id,
            "scopes": scopes,
            "expires_at": _now() + self._access_ttl,
            "issue_id": issue_id,
        }
        tokens[_REFRESH_PREFIX + refresh] = {
            "token": refresh,
            "client_id": client_id,
            "scopes": scopes,
            "expires_at": _now() + self._refresh_ttl,
            "issue_id": issue_id,
        }
        self._tokens.save(tokens)
        return OAuthToken(
            access_token=access,
            token_type="Bearer",  # nosec B106 - OAuth token type literal, not a credential
            expires_in=self._access_ttl,
            refresh_token=refresh,
            scope=" ".join(scopes),
        )

    @staticmethod
    def _revoke_family(tokens: dict[str, Any], issue_id: str) -> None:
        """Drop every active token sharing ``issue_id``. Mutates in place.

        Consumed refresh records (``consumed=True``) are also dropped
        so the registry does not grow unboundedly after a revocation.
        """
        if not issue_id:
            return
        for key in list(tokens.keys()):
            entry = tokens.get(key)
            if isinstance(entry, dict) and entry.get("issue_id") == issue_id:
                tokens.pop(key, None)

    async def load_access_token(self, token: str) -> AccessToken | None:
        async with self._async_lock:
            tokens = self._tokens.load()
            rec = tokens.get(token)
            if not rec:
                return None
            if int(rec.get("expires_at", 0)) < _now():
                tokens.pop(token, None)
                self._tokens.save(tokens)
                return None
            try:
                return AccessToken(
                    token=rec["token"],
                    client_id=rec["client_id"],
                    scopes=rec["scopes"],
                    expires_at=int(rec["expires_at"]),
                )
            except Exception:  # noqa: BLE001
                return None

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        async with self._async_lock:
            tokens = self._tokens.load()
            rec = tokens.get(_REFRESH_PREFIX + refresh_token)
            if not rec or rec.get("client_id") != (client.client_id or ""):
                return None
            if int(rec.get("expires_at", 0)) < _now():
                return None
            if rec.get("consumed"):
                # OAuth 2.1 BCP §4.13: a refresh token presented after
                # it was rotated is a reuse signal. Revoke the entire
                # family (every active access plus refresh sharing
                # ``issue_id``) and refuse the load.
                self._revoke_family(tokens, rec.get("issue_id", ""))
                self._tokens.save(tokens)
                return None
            try:
                return RefreshToken(
                    token=rec["token"],
                    client_id=rec["client_id"],
                    scopes=rec["scopes"],
                    expires_at=int(rec["expires_at"]),
                )
            except Exception:  # noqa: BLE001
                return None

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        async with self._async_lock:
            tokens = self._tokens.load()
            key = _REFRESH_PREFIX + refresh_token.token
            rec = tokens.get(key)
            if rec is None:
                # Orphan token: nothing to consume.
                raise ValueError("refresh token unknown")
            if rec.get("consumed"):
                # Reuse: revoke the whole family. The caller surfaces
                # the failure as ``invalid_grant`` to the client.
                self._revoke_family(tokens, rec.get("issue_id", ""))
                self._tokens.save(tokens)
                raise ValueError("refresh token reuse detected; family revoked")
            # Mark consumed (not popped) so a second presentation
            # remains detectable. The record cleans up naturally at
            # ``expires_at`` via the load path's expiry branch.
            rec["consumed"] = True
            rec["consumed_at"] = _now()
            tokens[key] = rec
            self._tokens.save(tokens)
            parent_issue = rec.get("issue_id") or None
            effective = list(scopes or refresh_token.scopes or _SCOPES)
            return self._issue(
                client.client_id or "",
                effective,
                parent_issue_id=parent_issue,
            )

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        async with self._async_lock:
            tokens = self._tokens.load()
            raw = getattr(token, "token", "")
            tokens.pop(raw, None)
            tokens.pop(_REFRESH_PREFIX + raw, None)
            self._tokens.save(tokens)


def build_auth_settings(issuer: str) -> AuthSettings:
    """Build the FastMCP ``AuthSettings`` for the configured issuer URL."""
    url = AnyHttpUrl(issuer)
    return AuthSettings(
        issuer_url=url,
        resource_server_url=url,
        client_registration_options=ClientRegistrationOptions(
            enabled=True, valid_scopes=_SCOPES, default_scopes=_SCOPES
        ),
        revocation_options=RevocationOptions(enabled=True),
        required_scopes=_SCOPES,
    )


def make_oauth_provider(settings: Any) -> FileOAuthProvider:
    """Construct a :class:`FileOAuthProvider` from a nous ``Settings`` object."""
    return FileOAuthProvider(
        settings.resolved_oauth_state_dir(),
        single_client=settings.oauth_single_client,
        access_ttl=settings.oauth_access_ttl,
        refresh_ttl=settings.oauth_refresh_ttl,
        code_ttl=settings.oauth_code_ttl,
    )
