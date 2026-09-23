"""Tests for license status parsing and client wiring."""

from __future__ import annotations

import aiohttp
from aresponses import ResponsesMockServer

from aiofortiosapi import (
    FortiCareRegistration,
    FortiCareSupport,
    FortiGuardConnection,
    FortiOSNotFoundError,
    LicenseStatus,
)
from aiofortiosapi.const import EP_LICENSE_STATUS

from .conftest import FAKE_HOST, json_response, load_fixture, make_client

FEATURE_COUNT = 47  # 49 envelope entries minus the dedicated fortiguard/forticare


def _feature(status: LicenseStatus, name: str):
    assert any(f.name == name for f in status.features), f"{name} missing"
    return next(f for f in status.features if f.name == name)


async def test_get_license_status_real_shape(aresponses: ResponsesMockServer) -> None:
    """Parse the sanitized capture from a real v8.0.1 FortiGate."""
    aresponses.add(
        FAKE_HOST,
        f"/{EP_LICENSE_STATUS}",
        "GET",
        json_response(load_fixture("v8_0/license_status.json")),
    )
    async with aiohttp.ClientSession() as session:
        status = await make_client(session).get_license_status()

    assert isinstance(status, LicenseStatus)
    assert len(status.features) == FEATURE_COUNT

    # FortiCare registration (sanitized fixture values)
    assert isinstance(status.forticare, FortiCareRegistration)
    assert status.forticare.status == "registered"
    assert status.forticare.registration_status == "registered"
    assert status.forticare.account == "user@example.com"
    # No support contract on this unit: empty support object -> safe defaults
    assert status.forticare.support == FortiCareSupport(level="", status="", expiry=0)

    # FortiGuard connectivity
    assert isinstance(status.fortiguard, FortiGuardConnection)
    assert status.fortiguard.connected is True
    assert status.fortiguard.connection_issue is False
    assert status.fortiguard.scheduled_updates_enabled is True
    assert status.fortiguard.last_connection_success > 0
    assert status.fortiguard.server_address == "update.example.com:443"

    # Paid feature, unlicensed, with entitlement + version
    ips = _feature(status, "ips")
    assert ips.kind == "downloaded_fds_object"
    assert ips.is_licensed is False
    assert ips.entitlement == "NIDS"
    assert ips.version == "6.00741"
    assert ips.last_update > 0

    # Bundled license: licensed but no entitlement field
    geoip = _feature(status, "geoip_db")
    assert geoip.is_licensed is True
    assert geoip.entitlement == ""

    # free_license counts as functional
    assert _feature(status, "forticloud_logging").is_licensed is True

    # Quota entry (platform)
    vdom = _feature(status, "vdom")
    assert vdom.kind == "platform"
    assert vdom.max > 0

    # Deviant shape: no type, no status
    ot = _feature(status, "ot_detection")
    assert ot.status == ""
    assert ot.is_licensed is False


def test_parse_empty_results() -> None:
    status = LicenseStatus.from_api({"results": {}})
    assert status.features == []
    assert status.forticare.status == ""
    assert status.fortiguard.connected is False


def test_parse_non_dict_results() -> None:
    status = LicenseStatus.from_api({"results": []})
    assert status.features == []


def test_parse_missing_results_key() -> None:
    status = LicenseStatus.from_api({})
    assert status.features == []
    assert status.fortiguard.server_address == ""


def test_parse_fortiguard_non_dict_entry() -> None:
    status = LicenseStatus.from_api({"results": {"fortiguard": None, "ips": {}}})
    assert status.fortiguard.connected is False
    assert status.features[0].name == "ips"


def test_parse_skips_non_dict_feature_entries() -> None:
    status = LicenseStatus.from_api({"results": {"ips": {}, "junk": "scalar"}})
    assert [f.name for f in status.features] == ["ips"]


def test_forticare_support_populated() -> None:
    raw = {
        "results": {
            "forticare": {
                "status": "registered",
                "support": {
                    "support_level": "24x7",
                    "status": "active",
                    "expiry": 1893456000,
                },
            }
        }
    }
    support = LicenseStatus.from_api(raw).forticare.support
    assert support == FortiCareSupport(level="24x7", status="active", expiry=1893456000)


def test_forticare_support_alternate_keys_and_string_date() -> None:
    raw = {
        "results": {
            "forticare": {
                "support": {"level": "8x5", "support_status": "active", "expiration": "2027-01-01"}
            }
        }
    }
    support = LicenseStatus.from_api(raw).forticare.support
    assert support.level == "8x5"
    assert support.status == "active"
    assert support.expiry == 0  # non-numeric tolerated


def test_forticare_support_non_dict_entry() -> None:
    raw = {"results": {"forticare": {"status": "registered", "support": None}}}
    support = LicenseStatus.from_api(raw).forticare.support
    assert support == FortiCareSupport(level="", status="", expiry=0)


async def test_license_status_404_raises_not_found(
    aresponses: ResponsesMockServer,
) -> None:
    """Firmware without the endpoint surfaces FortiOSNotFoundError (graceful)."""
    aresponses.add(FAKE_HOST, f"/{EP_LICENSE_STATUS}", "GET", aresponses.Response(status=404))
    async with aiohttp.ClientSession() as session:
        client = make_client(session)
        try:
            await client.get_license_status()
        except FortiOSNotFoundError:
            pass
        else:
            raise AssertionError("expected FortiOSNotFoundError")
