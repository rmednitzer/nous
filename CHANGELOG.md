# Changelog

All notable changes to `nous` land here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- OAuth 2.1 authorization-server provider (file-backed DCR + PKCE +
  rotating refresh, single-client lockdown) wired into the FastMCP HTTP
  transport. Caddy carveout for `/authorize` and `/.well-known/oauth-*`;
  set `NOUS_OAUTH_ENABLED=true` and `NOUS_OAUTH_ISSUER=https://...` to
  enable. Tracked by `BL-019`.
- v0.1 scaffold: project layout, governance docs, audited MCP tool
  surface, finite-state machine, tick-loop engine, hardware-profile
  loader, OAuth issuer shape, and typed stubs for subsystems, estimators,
  the self-model, and interop adapters. Tracked by `BL-001`.
