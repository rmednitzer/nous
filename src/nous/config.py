"""Typed, environment-driven configuration for the simulator.

All knobs read from ``NOUS_*`` environment variables (and an optional
``.env``). Invalid values fail fast at startup rather than mid-run, so a
misconfigured deployment cannot ship a partial state to disk.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["Settings", "get_settings"]

_TRANSPORTS = {"stdio", "http"}
_POLICY_MODES = {"open", "guarded", "readonly"}


class Settings(BaseSettings):
    """Effective simulator configuration. Immutable after load."""

    model_config = SettingsConfigDict(
        env_prefix="NOUS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    # Runtime
    home: Path = Field(default=Path("/var/lib/nous"))
    profile: str = "jetson-agx-orin"
    scenario: str = ""

    # Transport
    transport: Literal["stdio", "http"] = "stdio"
    http_bind: str = "127.0.0.1:8088"

    # Policy
    policy: Literal["open", "guarded", "readonly"] = "open"
    policy_deny: str = ""
    policy_allow: str = ""

    # Tick loop
    tick_hz: float = Field(default=2.0, gt=0.0, le=100.0)
    max_output: int = Field(default=65536, ge=1024)

    # Anthropic
    anthropic_api_key: SecretStr | None = None
    anthropic_daily_cap: int = Field(default=100, ge=0)
    anthropic_model_default: str = "claude-haiku-4-5-20251001"
    anthropic_model_advanced: str = "claude-sonnet-4-6"

    # Database
    db_url: str = ""

    # NATS (optional pub/sub for telemetry)
    nats_url: str | None = None

    # OAuth (HTTP transport only)
    oauth_enabled: bool = False
    oauth_issuer: str = "https://localhost:8088"
    oauth_state_dir: str = ""
    oauth_single_client: bool = True
    oauth_access_ttl: int = Field(default=3600, ge=60)
    oauth_refresh_ttl: int = Field(default=2_592_000, ge=300)
    oauth_code_ttl: int = Field(default=300, ge=30)

    # Audit
    audit_path: str = ""
    anchor_path: str = ""

    @field_validator("transport")
    @classmethod
    def _v_transport(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in _TRANSPORTS:
            raise ValueError(f"transport must be one of {sorted(_TRANSPORTS)}")
        return v

    @field_validator("policy")
    @classmethod
    def _v_policy(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in _POLICY_MODES:
            raise ValueError(f"policy must be one of {sorted(_POLICY_MODES)}")
        return v

    def resolved_audit_path(self) -> Path:
        return Path(self.audit_path) if self.audit_path else self.home / "audit.jsonl"

    def resolved_anchor_path(self) -> Path:
        if self.anchor_path:
            return Path(self.anchor_path)
        return self.resolved_audit_path().with_name("audit-anchors.jsonl")

    def resolved_db_url(self) -> str:
        if self.db_url:
            return self.db_url
        return f"sqlite:///{self.home}/state.db"

    def resolved_oauth_state_dir(self) -> Path:
        return Path(self.oauth_state_dir) if self.oauth_state_dir else self.home / "auth"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide cached settings instance."""
    return Settings()
