# Changelog

All notable changes to this project will be documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `FortiOSClient.get_license_status()` — FortiCare registration, FortiGuard
  connectivity, and per-feature entitlements from `monitor/license/status`,
  parsed into `LicenseStatus` / `FortiGuardConnection` / `FortiCareRegistration`
  / `LicenseFeature` (derived `is_licensed` covers `licensed` and
  `free_license`; bundled licenses without `entitlement` tolerated).
- `FortiCareSupport` — support level/status/expiry parsed from the FortiCare
  `support` object, with safe defaults when no contract is attached (`{}`).
- `LicenseFeature.license_kind` — derived entitlement kind ("paid",
  "bundled", "free", "none") distinguishing paid UTM licenses from bundled
  infrastructure databases and free cloud tiers.
- `FortiOSClient.get_firmware_status()` — running image and FortiGuard image
  catalog from `monitor/system/firmware`, parsed into `FirmwareStatus` /
  `FirmwareImage` with a derived `update_available` flag (any offered image
  newer than the running release).
- `FortiOSClient.get_wan_status()` — SD-WAN health-check results from
  `monitor/virtual-wan/health-check`, parsed into `SdwanHealthCheck` /
  `SdwanHealthCheckMember` with a derived `sla_met` flag (a member can be
  "up" while violating its SLA — both states are exposed).
- `FortiOSClient.get_interfaces()` — per-interface link state, addressing
  and traffic counters from `monitor/system/interface`, parsed into
  `InterfaceStatus` (dict envelope, sorted by name).
- `parse_fortios_version()` / `VersionInfo` — dependency-free parsing of
  FortiOS version strings (`v8.0.1`, `v7.6.7 build3704 (M)`, …) with
  tuple-comparable release info.
- Defensive-parsing contract documented: missing firmware fields default
  instead of raising; absent endpoints raise `FortiOSNotFoundError` so
  callers can degrade per feature.

## [0.1.0] - 2026-08-26

### Added
- Initial scaffold: `FortiOSClient` with Bearer token auth and injected `aiohttp.ClientSession`.
- `get_system_status()`, `get_resource_usage()`, `get_detected_devices()` endpoints.
- `async_validate()` for cheap credential validation in HA config_flow.
- `FortiOSClient.get(path, *, params=None)` — generic raw-envelope GET for
  endpoints without a dedicated typed method (e.g. HA coordinator polling).
- Exception hierarchy: `FortiOSConnectionError`, `FortiOSAuthenticationError`,
  `FortiOSNotFoundError`, `FortiOSResponseError`.
- Typed frozen dataclasses: `SystemStatus`, `ResourceUsage`, `DetectedDevice`.
- `verify_ssl` flag for self-signed FortiGate certificates.
- `vdom` parameter support.
- Full test suite using `aresponses` (no live network required).
- Ruff + mypy strict configuration.
- GitHub Actions CI (lint + test on Python 3.12/3.13/3.14) and OIDC-based PyPI release workflow.

### Changed
- `DetectedDevice.is_online` uses the API-reported `is_online` flag; when a
  firmware omits the field it falls back to `last_seen` freshness (seen within
  the new `device_online_threshold` client argument, default 300 s).
  `DetectedDevice.list_from_api()` accepts keyword-only `now` and
  `online_threshold` for deterministic parsing.
- `ResourceUsage` model matches real firmware: memory under `"mem"`/`"current"`,
  `sessions` and `session_setup_rate` sum IPv4+IPv6 buckets; `uptime` was
  dropped (not present on `monitor/system/resource/usage`).

### Fixed
- `DetectedDevice.ip` no longer becomes the string `"None"` when the API returns
  a null `ipv4_address`; all string fields map null to `""`.
- Parsing no longer raises on scalar list entries (`_first`), null envelopes
  (`"results": null`), or non-numeric stat values; safe defaults are used.
- Error messages for failed requests surface FortiOS detail keys (`cli_error`,
  `message`, `error`, `http_message`) instead of an often-empty `error`,
  falling back to the truncated raw body.
