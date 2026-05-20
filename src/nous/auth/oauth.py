"""File-backed OAuth 2.1 issuer (skeleton for the HTTP transport).

State lives in three JSON files under ``$NOUS_HOME/auth/``:
``clients.json``, ``codes.json``, ``tokens.json``. Each file is read and
rewritten atomically; no database is required.

This is the v0.1 shape. The full L2 implementation (BL-019) wires it into
FastMCP via the SDK's ``OAuthAuthorizationServerProvider``.
"""

from __future__ import annotations

import json
import secrets
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

__all__ = ["OAuthIssuer", "RegisteredClient", "Token"]


class RegisteredClient(BaseModel):
    client_id: str
    client_secret: str = ""
    redirect_uris: list[str] = Field(default_factory=list)
    scopes: list[str] = Field(default_factory=lambda: ["mcp:tools"])


class Token(BaseModel):
    access_token: str
    refresh_token: str
    expires_at: int
    refresh_expires_at: int
    client_id: str
    scopes: list[str] = Field(default_factory=lambda: ["mcp:tools"])


class _JsonStore:
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
        tmp.replace(self._path)


class OAuthIssuer:
    """OAuth 2.1 authorization-server skeleton with file-backed state."""

    def __init__(
        self,
        state_dir: Path,
        *,
        single_client: bool = True,
        access_ttl: int = 3600,
        refresh_ttl: int = 2_592_000,
        code_ttl: int = 300,
    ) -> None:
        self._clients = _JsonStore(state_dir / "clients.json")
        self._codes = _JsonStore(state_dir / "codes.json")
        self._tokens = _JsonStore(state_dir / "tokens.json")
        self._single_client = single_client
        self._access_ttl = access_ttl
        self._refresh_ttl = refresh_ttl
        self._code_ttl = code_ttl

    def register_client(
        self, redirect_uris: list[str] | None = None
    ) -> RegisteredClient:
        """Register a new OAuth client, or return the single locked-in one."""
        clients = self._clients.load()
        if self._single_client and clients:
            existing = next(iter(clients.values()))
            return RegisteredClient.model_validate(existing)
        client = RegisteredClient(
            client_id=secrets.token_urlsafe(16),
            client_secret=secrets.token_urlsafe(32),
            redirect_uris=list(redirect_uris or []),
        )
        clients[client.client_id] = client.model_dump()
        self._clients.save(clients)
        return client

    def authorize(self, client_id: str, redirect_uri: str) -> str:
        """Issue a short-lived authorization code."""
        code = secrets.token_urlsafe(32)
        codes = self._codes.load()
        codes[code] = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "expires_at": int(time.time()) + self._code_ttl,
        }
        self._codes.save(codes)
        return code

    def token(self, code: str) -> Token | None:
        """Exchange an authorization code for an access + refresh token."""
        codes = self._codes.load()
        entry = codes.pop(code, None)
        self._codes.save(codes)
        if not entry or int(entry.get("expires_at", 0)) < int(time.time()):
            return None
        return self._issue_token(str(entry["client_id"]))

    def refresh(self, refresh_token: str) -> Token | None:
        """Issue a new access token from a rotating refresh token."""
        tokens = self._tokens.load()
        entry = tokens.pop(f"refresh:{refresh_token}", None)
        if entry is None or int(entry.get("expires_at", 0)) < int(time.time()):
            self._tokens.save(tokens)
            return None
        self._tokens.save(tokens)
        return self._issue_token(str(entry["client_id"]))

    def introspect(self, access_token: str) -> Token | None:
        """Return token metadata if the access token is live."""
        tokens = self._tokens.load()
        entry = tokens.get(f"access:{access_token}")
        if entry is None or int(entry.get("expires_at", 0)) < int(time.time()):
            return None
        return Token.model_validate(entry)

    def _issue_token(self, client_id: str) -> Token:
        now = int(time.time())
        access = secrets.token_urlsafe(32)
        refresh = secrets.token_urlsafe(32)
        token = Token(
            access_token=access,
            refresh_token=refresh,
            expires_at=now + self._access_ttl,
            refresh_expires_at=now + self._refresh_ttl,
            client_id=client_id,
        )
        tokens = self._tokens.load()
        tokens[f"access:{access}"] = token.model_dump()
        tokens[f"refresh:{refresh}"] = {
            "client_id": client_id,
            "expires_at": now + self._refresh_ttl,
        }
        self._tokens.save(tokens)
        return token
