"""Frozen dataclasses for parsed FortiOS API responses.

FortiOS wraps all payloads as:
  {"results": <dict|list>, "status": "success", "version": "v7.6.1",
   "serial": "FGT60F...", "vdom": "root", ...}

Each model's from_api() accepts the full envelope dict and parses defensively:
missing keys, null values, and unexpected shapes all fall back to safe
defaults instead of raising.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from .const import DEFAULT_ONLINE_THRESHOLD


def _first(lst: Any, key: str, default: Any = None) -> Any:
    """Extract key from the first element of a list of dicts, or default.

    FortiOS returns cpu/memory/session stats as single-element lists of
    objects; tolerate scalar lists, empty lists, and non-list values.
    """
    if isinstance(lst, list) and lst and isinstance(lst[0], dict):
        return lst[0].get(key, default)
    return default


def _as_str(value: Any) -> str:
    """Coerce an optional API string field to str; null and non-str become ''."""
    return value if isinstance(value, str) else ""


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True, slots=True)
class SystemStatus:
    """Parsed response from monitor/system/status."""

    hostname: str
    version: str
    serial: str
    model: str

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> SystemStatus:
        results: Any = raw.get("results")
        if not isinstance(results, dict):
            results = {}
        serial = _as_str(raw.get("serial") or results.get("Serial-Number"))
        version = _as_str(raw.get("version") or results.get("Version"))
        hostname = _as_str(results.get("Hostname") or results.get("hostname"))
        # Model name: use FGVM/FGT prefix from serial when not explicit
        model = _as_str(results.get("Model-Name") or results.get("model") or serial[:6])
        return cls(hostname=hostname, version=version, serial=serial, model=model)


@dataclass(frozen=True, slots=True)
class ResourceUsage:
    """Parsed response from monitor/system/resource/usage.

    Real FortiOS (verified on v8.0.1) returns each metric as a single-element
    list with a ``current`` value, and splits sessions/setup-rate into IPv4
    and IPv6 buckets:

    ``{"cpu": [{"current": 0}], "mem": [{"current": 34}],
       "session": [{"current": 279}], "session6": [{"current": 57}],
       "setuprate": [{"current": 7}], "setuprate6": [{"current": 0}], ...}``

    ``sessions`` and ``session_setup_rate`` are the sum of the v4 + v6
    buckets.
    """

    cpu_percent: float
    memory_percent: float
    sessions: int  # session + session6
    session_setup_rate: int  # setuprate + setuprate6

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> ResourceUsage:
        results: Any = raw.get("results")
        if not isinstance(results, dict):
            results = {}
        return cls(
            cpu_percent=_to_float(_first(results.get("cpu"), "current")),
            memory_percent=_to_float(_first(results.get("mem"), "current")),
            sessions=(
                _to_int(_first(results.get("session"), "current"))
                + _to_int(_first(results.get("session6"), "current"))
            ),
            session_setup_rate=(
                _to_int(_first(results.get("setuprate"), "current"))
                + _to_int(_first(results.get("setuprate6"), "current"))
            ),
        )


@dataclass(frozen=True, slots=True)
class DetectedDevice:
    """A single device from monitor/user/device/query.

    Consumed by the Home Assistant device_tracker platform.

    FortiOS reports an ``is_online`` flag for detected devices, which is used
    verbatim.  When a firmware omits the field, ``is_online`` is derived from
    ``last_seen`` freshness instead: True when the device was seen within
    ``online_threshold`` seconds of the reference time (default
    ``DEFAULT_ONLINE_THRESHOLD``, mirroring HA's consider_home behaviour).
    """

    mac: str
    hostname: str
    ip: str  # primary IP; may be empty string if unknown
    os_name: str
    interface: str
    last_seen: int  # unix timestamp; 0 when not available
    is_online: bool  # API-reported; derived from last_seen when absent

    @classmethod
    def _from_entry(
        cls,
        entry: dict[str, Any],
        *,
        now: float,
        online_threshold: float,
    ) -> DetectedDevice:
        # IPs may come as a list, a plain string, or null
        ips: Any = entry.get("ipv4_address", entry.get("ip"))
        if isinstance(ips, list):
            ip = _as_str(ips[0]) if ips else ""
        elif isinstance(ips, str):
            ip = ips
        else:
            ip = ""

        last_seen = _to_int(entry.get("last_seen"))

        api_flag = entry.get("is_online")
        if api_flag is None:
            # Field absent on this firmware: fall back to freshness.
            is_online = last_seen > 0 and (now - float(last_seen)) <= online_threshold
        else:
            is_online = bool(api_flag)

        return cls(
            mac=_as_str(entry.get("mac")),
            hostname=_as_str(entry.get("hostname") or entry.get("name")),
            ip=ip,
            os_name=_as_str(entry.get("os_name") or entry.get("os")),
            interface=_as_str(entry.get("interface")),
            last_seen=last_seen,
            is_online=is_online,
        )

    @classmethod
    def list_from_api(
        cls,
        raw: dict[str, Any],
        *,
        now: float | None = None,
        online_threshold: float = DEFAULT_ONLINE_THRESHOLD,
    ) -> list[DetectedDevice]:
        """Parse the device list envelope.

        ``now`` and ``online_threshold`` only affect the freshness-based
        fallback used when an entry carries no ``is_online`` field.  ``now``
        defaults to the current wall clock; pass it explicitly in tests.
        """
        results = raw.get("results", [])
        if not isinstance(results, list):
            return []
        reference_now = time.time() if now is None else now
        return [
            cls._from_entry(e, now=reference_now, online_threshold=online_threshold)
            for e in results
            if isinstance(e, dict)
        ]


# Statuses that mean a license feature is fully functional.  FortiOS also
# reports e.g. "registered" (FortiCare), "cloud_na", or omits the field for
# non-entitlement entries — those are not licensed features.
_LICENSED_STATUSES = frozenset({"licensed", "free_license"})


@dataclass(frozen=True, slots=True)
class LicenseFeature:
    """One license entitlement entry from monitor/license/status.

    Covers all entry archetypes (downloaded_fds_object, live_fortiguard_service,
    live_cloud_service, platform quotas, …) with tolerant optional fields:
    anything the entry does not carry defaults to ""/0 instead of raising.
    """

    name: str  # envelope key, e.g. "ips"
    kind: str  # the entry "type", e.g. "downloaded_fds_object"
    status: str  # "licensed", "no_license", "free_license", "" when absent
    is_licensed: bool  # derived: status in {"licensed", "free_license"}
    entitlement: str  # e.g. "NIDS"; bundled licenses omit this
    version: str  # signature/database version, e.g. "6.00741"
    last_update: int  # unix timestamp; 0 when absent
    used: int  # quota usage (vdom, sms); 0 otherwise
    max: int  # quota limit (vdom, sms); 0 otherwise

    @property
    def license_kind(self) -> str:
        """Derive the entitlement kind from status and entitlement.

        Heuristic (derived, not API-reported): ``free_license`` → "free";
        ``licensed`` with an ``entitlement`` → "paid"; ``licensed`` without
        → "bundled" (infrastructure databases every unit includes);
        anything else → "none".
        """
        if self.status == "free_license":
            return "free"
        if self.status == "licensed":
            return "paid" if self.entitlement else "bundled"
        return "none"

    @classmethod
    def _from_entry(cls, name: str, entry: dict[str, Any]) -> LicenseFeature:
        status = _as_str(entry.get("status"))
        return cls(
            name=name,
            kind=_as_str(entry.get("type")),
            status=status,
            is_licensed=status in _LICENSED_STATUSES,
            entitlement=_as_str(entry.get("entitlement")),
            version=_as_str(entry.get("version")),
            last_update=_to_int(entry.get("last_update")),
            used=_to_int(entry.get("used")),
            max=_to_int(entry.get("max")),
        )


@dataclass(frozen=True, slots=True)
class FortiGuardConnection:
    """FortiGuard distribution service connectivity (from license/status)."""

    connected: bool
    connection_issue: bool
    supported: bool
    scheduled_updates_enabled: bool
    last_connection_success: int  # unix timestamp; 0 when never
    next_scheduled_update: int  # unix timestamp; 0 when unknown
    server_address: str

    @classmethod
    def from_api(cls, entry: Any) -> FortiGuardConnection:
        if not isinstance(entry, dict):
            entry = {}
        return cls(
            connected=bool(entry.get("connected", False)),
            connection_issue=bool(entry.get("connection_issue", False)),
            supported=bool(entry.get("supported", False)),
            scheduled_updates_enabled=bool(entry.get("scheduled_updates_enabled", False)),
            last_connection_success=_to_int(entry.get("last_connection_success")),
            next_scheduled_update=_to_int(entry.get("next_scheduled_update")),
            server_address=_as_str(entry.get("server_address")),
        )


@dataclass(frozen=True, slots=True)
class FortiCareSupport:
    """Support entitlement details from license/status.

    Empty values mean no support contract is attached — on such units the
    ``support`` object is ``{}``.  Key names vary across firmware; common
    variants are tried and unrecognized values default safely.  The
    populated-case key variants are unverified against real hardware (only
    the empty case is); parsing stays defensive on purpose.
    """

    level: str  # e.g. "8x5" / "24x7"
    status: str  # e.g. "active"
    expiry: int  # unix timestamp; 0 when unknown or non-numeric

    @classmethod
    def from_api(cls, entry: Any) -> FortiCareSupport:
        if not isinstance(entry, dict):
            entry = {}
        return cls(
            level=_as_str(entry.get("support_level") or entry.get("level")),
            status=_as_str(entry.get("status") or entry.get("support_status")),
            expiry=_to_int(entry.get("expiry") or entry.get("expiration")),
        )


@dataclass(frozen=True, slots=True)
class FortiCareRegistration:
    """FortiCare registration state (from license/status)."""

    status: str  # e.g. "registered"
    registration_status: str  # same value via a second field on some firmware
    account: str  # registered account email
    company: str
    support: FortiCareSupport

    @classmethod
    def from_api(cls, entry: Any) -> FortiCareRegistration:
        if not isinstance(entry, dict):
            entry = {}
        return cls(
            status=_as_str(entry.get("status")),
            registration_status=_as_str(entry.get("registration_status")),
            account=_as_str(entry.get("account")),
            company=_as_str(entry.get("company")),
            support=FortiCareSupport.from_api(entry.get("support")),
        )


@dataclass(frozen=True, slots=True)
class LicenseStatus:
    """Parsed response from monitor/license/status.

    ``fortiguard`` and ``forticare`` get dedicated models because they are
    cloud-service entries rather than feature entitlements.  Every other
    envelope key becomes a :class:`LicenseFeature`, sorted by name for
    deterministic ordering.
    """

    fortiguard: FortiGuardConnection
    forticare: FortiCareRegistration
    features: list[LicenseFeature]

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> LicenseStatus:
        results: Any = raw.get("results")
        if not isinstance(results, dict):
            results = {}
        features = [
            LicenseFeature._from_entry(str(name), entry)
            for name, entry in sorted(results.items())
            if name not in ("fortiguard", "forticare") and isinstance(entry, dict)
        ]
        return cls(
            fortiguard=FortiGuardConnection.from_api(results.get("fortiguard")),
            forticare=FortiCareRegistration.from_api(results.get("forticare")),
            features=features,
        )
