"""Tests for model parsing."""

from __future__ import annotations

from aiofortiosapi.models import DetectedDevice, ResourceUsage, SystemStatus

from .conftest import load_fixture


def test_system_status_from_fixture() -> None:
    raw = load_fixture("system_status.json")
    status = SystemStatus.from_api(raw)
    assert status.hostname == "homelab-fw"
    assert status.version == "v7.6.1"
    assert status.serial == "FGT60FXXXXXXXX"
    assert status.model == "FortiGate-60F"


def test_resource_usage_list_shape() -> None:
    """Parses the real v8.0.1 envelope (cpu/mem/current + session6/setuprate6)."""
    raw = load_fixture("resource_usage.json")
    usage = ResourceUsage.from_api(raw)
    assert usage.cpu_percent == 0.0
    assert usage.memory_percent == 34.0
    assert usage.sessions == 279 + 57
    assert usage.session_setup_rate == 7


def test_resource_usage_missing_keys() -> None:
    usage = ResourceUsage.from_api({"results": {}})
    assert usage.cpu_percent == 0.0
    assert usage.memory_percent == 0.0
    assert usage.sessions == 0
    assert usage.session_setup_rate == 0


def test_detected_device_list_from_api() -> None:
    raw = load_fixture("detected_devices.json")
    devices = DetectedDevice.list_from_api(raw)
    assert len(devices) == 2
    d = devices[0]
    assert d.mac == "aa:bb:cc:dd:ee:01"
    assert d.hostname == "laptop-alice"
    assert d.ip == "192.168.1.10"
    assert d.os_name == "Windows 11"
    assert d.interface == "internal"
    assert d.last_seen == 1750000000
    # API-reported flags are used verbatim
    assert d.is_online is True
    assert devices[1].is_online is False


def test_detected_device_api_flag_overrides_freshness() -> None:
    """A reported is_online flag wins even when it contradicts last_seen."""
    raw = {
        "results": [
            {"mac": "aa", "last_seen": 100, "is_online": True},  # ancient but flagged online
            {"mac": "bb", "last_seen": 1_000_095, "is_online": False},  # fresh but flagged offline
            {"mac": "cc", "last_seen": 1_000_095},  # no flag: fallback derivation applies
        ]
    }
    devices = DetectedDevice.list_from_api(raw, now=1_000_000.0, online_threshold=300.0)
    assert devices[0].is_online is True
    assert devices[1].is_online is False
    assert devices[2].is_online is True


def test_detected_device_online_threshold() -> None:
    now = 1_000_000.0
    raw = {
        "results": [
            {"mac": "aa", "last_seen": 999_950},  # 50s ago
            {"mac": "bb", "last_seen": 999_600},  # 400s ago
        ]
    }
    devices = DetectedDevice.list_from_api(raw, now=now, online_threshold=300.0)
    assert devices[0].is_online is True
    assert devices[1].is_online is False


def test_detected_device_never_seen_is_offline() -> None:
    raw = {"results": [{"mac": "cc"}]}
    d = DetectedDevice.list_from_api(raw, now=1_000_000.0)[0]
    assert d.last_seen == 0
    assert d.is_online is False


def test_detected_device_future_last_seen_is_online() -> None:
    """Clock skew (FortiGate ahead of host) must not mark devices offline."""
    raw = {"results": [{"mac": "dd", "last_seen": 1_000_100}]}
    d = DetectedDevice.list_from_api(raw, now=1_000_000.0)[0]
    assert d.is_online is True


def test_detected_device_null_fields_become_empty_strings() -> None:
    raw = {
        "results": [
            {
                "mac": None,
                "hostname": None,
                "ipv4_address": None,
                "os_name": None,
                "interface": None,
                "last_seen": None,
                "is_online": None,
            }
        ]
    }
    d = DetectedDevice.list_from_api(raw, now=0.0)[0]
    assert d.mac == ""
    assert d.hostname == ""
    assert d.ip == ""  # null ipv4_address must not become the string "None"
    assert d.os_name == ""
    assert d.interface == ""
    assert d.last_seen == 0
    # null flag falls back to freshness derivation; last_seen 0 => offline
    assert d.is_online is False


def test_detected_device_hostname_falls_back_to_name() -> None:
    raw = {"results": [{"hostname": None, "name": "printer", "ip": "10.0.0.5"}]}
    d = DetectedDevice.list_from_api(raw, now=0.0)[0]
    assert d.hostname == "printer"
    assert d.ip == "10.0.0.5"


def test_detected_device_skips_non_dict_entries() -> None:
    raw = {"results": [{"mac": "ee"}, "garbage", None]}
    devices = DetectedDevice.list_from_api(raw, now=0.0)
    assert len(devices) == 1
    assert devices[0].mac == "ee"


def test_resource_usage_scalar_list_entries() -> None:
    """Malformed entries fall back to defaults; valid entries still sum correctly."""
    usage = ResourceUsage.from_api(
        {
            "results": {
                "cpu": [5],  # scalar list -> _first guard rejects -> 0
                "mem": [{"current": "66"}],  # numeric string -> _to_float accepts -> 66
                "session": [{"current": None}],  # None current -> _to_int rejects -> 0
                "session6": [{"current": 4}],  # valid -> 4
                "setuprate": [{"current": "abc"}],  # non-numeric string -> 0
                "setuprate6": [{"current": 2}],  # valid -> 2
            }
        }
    )
    assert usage.cpu_percent == 0.0
    assert usage.memory_percent == 66.0
    assert usage.sessions == 0 + 4
    assert usage.session_setup_rate == 0 + 2


def test_resource_usage_null_results() -> None:
    usage = ResourceUsage.from_api({"results": None})
    assert usage.cpu_percent == 0.0
    assert usage.memory_percent == 0.0
    assert usage.sessions == 0
    assert usage.session_setup_rate == 0


def test_system_status_null_results_and_serial() -> None:
    status = SystemStatus.from_api({"serial": None, "version": None, "results": None})
    assert status.hostname == ""
    assert status.version == ""
    assert status.serial == ""
    assert status.model == ""


def test_detected_device_ip_as_list() -> None:
    raw = {"results": [{"mac": "00:11:22:33:44:55", "ipv4_address": ["10.0.0.1", "10.0.0.2"]}]}
    devices = DetectedDevice.list_from_api(raw)
    assert devices[0].ip == "10.0.0.1"


def test_detected_device_empty_results() -> None:
    assert DetectedDevice.list_from_api({"results": []}) == []
    assert DetectedDevice.list_from_api({}) == []
    assert DetectedDevice.list_from_api({"results": None}) == []


def test_system_status_missing_optional_fields() -> None:
    raw = {"serial": "FGT90E123", "version": "v7.4.0", "results": {}}
    status = SystemStatus.from_api(raw)
    assert status.serial == "FGT90E123"
    assert status.version == "v7.4.0"
    assert status.hostname == ""
    assert status.model == "FGT90E"  # first 6 chars of serial
