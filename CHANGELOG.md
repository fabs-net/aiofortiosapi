# Changelog

All notable changes to this project will be documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- `DetectedDevice.ip` no longer becomes the string `"None"` when the API returns
  a null `ipv4_address`; all string fields now map null to `""`.
- Parsing no longer raises on scalar list entries (`_first`), null envelopes
  (`"results": null`), or non-numeric stat values; safe defaults are used.
- Error messages for failed requests now surface FortiOS detail keys
  (`cli_error`, `message`, `error`, `http_message`) instead of often-empty
  `error`, falling back to the truncated raw body.
- `ResourceUsage.from_api` now reads the real firmware keys: memory lives
  under `"mem"` with field `"current"` (previously parsed a fictional
  `"memory"`/`"used_percent"`), sessions sum v4+v6, and a setup-rate field is
  exposed.  `uptime` was dropped — that key does not exist on
  `monitor/system/resource/usage`.

### Added
- `FortiOSClient.get(path, *, params=None)` — generic raw-envelope GET for
  endpoints without a dedicated typed method (e.g. HA coordinator polling).

### Changed
- `DetectedDevice.is_online` now uses the API-reported `is_online` flag.
  When a firmware omits the field, online state falls back to `last_seen`
  freshness (seen within the new `device_online_threshold` client argument,
  default 300 s); `DetectedDevice.list_from_api()` accepts keyword-only
  `now` and `online_threshold` for deterministic parsing.
- `ResourceUsage` model updated: dropped `uptime`, added `session_setup_rate`,
  `sessions` and `session_setup_rate` now sum IPv4+IPv6 buckets.

## [0.1.0] - Unreleased

### Added
- Initial scaffold: `FortiOSClient` with Bearer token auth and injected `aiohttp.ClientSession`.
- `get_system_status()`, `get_resource_usage()`, `get_detected_devices()` endpoints.
- `async_validate()` for cheap credential validation in HA config_flow.
- Exception hierarchy: `FortiOSConnectionError`, `FortiOSAuthenticationError`,
  `FortiOSNotFoundError`, `FortiOSResponseError`.
- Typed frozen dataclasses: `SystemStatus`, `ResourceUsage`, `DetectedDevice`.
- `verify_ssl` flag for self-signed FortiGate certificates.
- `vdom` parameter support.
- Full test suite using `aresponses` (no live network required).
- Ruff + mypy strict configuration.
- GitHub Actions CI (lint + test on Python 3.12/3.13/3.14) and OIDC-based PyPI release workflow.
