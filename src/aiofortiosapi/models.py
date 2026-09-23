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
from .versions import parse_fortios_version


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


@dataclass(frozen=True, slots=True)
class FirmwareImage:
    """One firmware image entry from monitor/system/firmware.

    ``current`` carries ``source="current"`` and a ``platform-id``;
    ``available`` images come from FortiGuard with opaque image ids.
    All fields default safely when a firmware omits them.
    """

    name: str  # e.g. "FortiOS"
    image_id: str  # API "id"; "current" for the running image
    version: str  # e.g. "v8.0.1"
    major: int
    minor: int
    patch: int
    build: int
    release_type: str  # API "release-type", e.g. "GA"
    maturity: str  # "F" (feature) or "M" (maturity)
    source: str  # "current" or "fortiguard"
    notes_url: str  # release notes URL

    @property
    def release(self) -> tuple[int, int, int]:
        """Return the (major, minor, patch) tuple for comparisons."""
        return (self.major, self.minor, self.patch)

    @classmethod
    def from_api(cls, entry: Any) -> FirmwareImage:
        if not isinstance(entry, dict):
            entry = {}
        major = _to_int(entry.get("major"))
        minor = _to_int(entry.get("minor"))
        patch = _to_int(entry.get("patch"))
        version = _as_str(entry.get("version"))
        if not (major or minor or patch):
            # Firmware omitted the numeric fields: derive them from the
            # version string ("v8.0.1" -> 8, 0, 1).
            parsed = parse_fortios_version(version)
            if parsed is not None:
                major, minor, patch = parsed.major, parsed.minor, parsed.patch
        return cls(
            name=_as_str(entry.get("name")),
            image_id=_as_str(entry.get("id")),
            version=version,
            major=major,
            minor=minor,
            patch=patch,
            build=_to_int(entry.get("build")),
            release_type=_as_str(entry.get("release-type")),
            maturity=_as_str(entry.get("maturity")),
            source=_as_str(entry.get("source")),
            notes_url=_as_str(entry.get("notes")),
        )


@dataclass(frozen=True, slots=True)
class FirmwareStatus:
    """Parsed response from monitor/system/firmware.

    ``update_available`` compares release tuples and is True when any
    available image is newer than the running one.  Maturity and release
    type are not filtered — a maintenance build offered by FortiGuard
    counts as an update.
    """

    current: FirmwareImage
    available: list[FirmwareImage]
    update_available: bool

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> FirmwareStatus:
        results: Any = raw.get("results")
        if not isinstance(results, dict):
            results = {}
        current = FirmwareImage.from_api(results.get("current"))
        available = [
            FirmwareImage.from_api(entry)
            for entry in (results.get("available") or [])
            if isinstance(entry, dict)
        ]
        update_available = any(image.release > current.release for image in available)
        return cls(current=current, available=available, update_available=update_available)


@dataclass(frozen=True, slots=True)
class SdwanHealthCheckMember:
    """One member-interface result within an SD-WAN health check.

    ``status`` is the API-reported link state for this check; ``sla_met`` is
    derived from ``sla_targets_met`` (non-empty list means at least one SLA
    target is met).  The two can legitimately diverge: a member can be
    "up" while violating its SLA (e.g. high latency or packet loss).
    """

    interface: str  # member interface name, e.g. "wan1"
    status: str  # "up" | "down"
    sla_met: bool  # derived: non-empty sla_targets_met list
    latency_ms: float
    jitter_ms: float
    packet_loss_percent: float
    packets_sent: int
    packets_received: int
    tx_bandwidth_kbps: int
    rx_bandwidth_kbps: int
    state_changed: int  # unix timestamp of last state change; 0 when absent

    @classmethod
    def _from_entry(cls, interface: str, entry: dict[str, Any]) -> SdwanHealthCheckMember:
        targets: Any = entry.get("sla_targets_met")
        return cls(
            interface=interface,
            status=_as_str(entry.get("status")),
            sla_met=bool(targets) if isinstance(targets, list) else False,
            latency_ms=_to_float(entry.get("latency")),
            jitter_ms=_to_float(entry.get("jitter")),
            packet_loss_percent=_to_float(entry.get("packet_loss")),
            packets_sent=_to_int(entry.get("packet_sent")),
            packets_received=_to_int(entry.get("packet_received")),
            tx_bandwidth_kbps=_to_int(entry.get("tx_bandwidth")),
            rx_bandwidth_kbps=_to_int(entry.get("rx_bandwidth")),
            state_changed=_to_int(entry.get("state_changed")),
        )


@dataclass(frozen=True, slots=True)
class SdwanHealthCheck:
    """One named SD-WAN health check and its per-member results.

    Parsed from monitor/virtual-wan/health-check, whose envelope maps
    check name → member interface → metrics.  Checks are sorted by name.
    """

    name: str  # e.g. "Default_DNS"
    members: list[SdwanHealthCheckMember]

    @classmethod
    def list_from_api(cls, raw: dict[str, Any]) -> list[SdwanHealthCheck]:
        """Parse the health-check envelope (check name → interface → metrics)."""
        results: Any = raw.get("results")
        if not isinstance(results, dict):
            results = {}
        checks = [
            cls(
                name=str(check_name),
                members=[
                    SdwanHealthCheckMember._from_entry(str(interface), member)
                    for interface, member in sorted(check_entry.items())
                    if isinstance(member, dict)
                ],
            )
            for check_name, check_entry in sorted(results.items())
            if isinstance(check_entry, dict)
        ]
        return checks


@dataclass(frozen=True, slots=True)
class InterfaceStatus:
    """Link state, addressing and traffic counters for one interface.

    Parsed from monitor/system/interface, whose envelope maps interface
    name → status.  Interfaces are sorted by name.  Unconfigured ports
    report ip "0.0.0.0", mask 0 and speed 0.0.
    """

    name: str  # e.g. "wan1"
    alias: str  # configured alias; "" when unset
    ip: str  # primary IPv4; "0.0.0.0" when unconfigured
    prefix_len: int  # e.g. 24; 0 when unconfigured
    link: bool
    speed_mbps: float  # negotiated speed; 0.0 when down
    duplex: int  # raw API enum (1 = full)
    mac: str
    tx_bytes: int
    rx_bytes: int
    tx_packets: int
    rx_packets: int
    tx_errors: int
    rx_errors: int

    @classmethod
    def list_from_api(cls, raw: dict[str, Any]) -> list[InterfaceStatus]:
        """Parse the interface envelope (interface name → status)."""
        results: Any = raw.get("results")
        if not isinstance(results, dict):
            results = {}
        return [
            cls(
                name=_as_str(entry.get("name")) or str(ifname),
                alias=_as_str(entry.get("alias")),
                ip=_as_str(entry.get("ip")),
                prefix_len=_to_int(entry.get("mask")),
                link=bool(entry.get("link", False)),
                speed_mbps=_to_float(entry.get("speed")),
                duplex=_to_int(entry.get("duplex")),
                mac=_as_str(entry.get("mac")),
                tx_bytes=_to_int(entry.get("tx_bytes")),
                rx_bytes=_to_int(entry.get("rx_bytes")),
                tx_packets=_to_int(entry.get("tx_packets")),
                rx_packets=_to_int(entry.get("rx_packets")),
                tx_errors=_to_int(entry.get("tx_errors")),
                rx_errors=_to_int(entry.get("rx_errors")),
            )
            for ifname, entry in sorted(results.items())
            if isinstance(entry, dict)
        ]
