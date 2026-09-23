"""Tests for SD-WAN health check and interface status parsing."""

from __future__ import annotations

import aiohttp
from aresponses import ResponsesMockServer

from aiofortiosapi import (
    FortiOSNotFoundError,
    InterfaceStatus,
    SdwanHealthCheck,
    SdwanHealthCheckMember,
)
from aiofortiosapi.const import (
    EP_CMDB_INTERFACES,
    EP_INTERFACES,
    EP_SDWAN_HEALTH_CHECK,
)

from .conftest import FAKE_HOST, json_response, load_fixture, make_client


def _check(checks: list[SdwanHealthCheck], name: str) -> SdwanHealthCheck:
    assert any(c.name == name for c in checks), f"{name} missing"
    return next(c for c in checks if c.name == name)


async def test_get_wan_status_real_shape(aresponses: ResponsesMockServer) -> None:
    """Parse the sanitized capture from a real v8.0.1 FortiGate."""
    aresponses.add(
        FAKE_HOST,
        f"/{EP_SDWAN_HEALTH_CHECK}",
        "GET",
        json_response(load_fixture("v8_0/sdwan_health_check.json")),
    )
    async with aiohttp.ClientSession() as session:
        checks = await make_client(session).get_wan_status()

    # Sorted, all three checks present, each with one member (wan1)
    assert [c.name for c in checks] == ["Default_DNS", "Default_FortiGuard", "Default_Gmail"]
    assert all(len(c.members) == 1 for c in checks)

    dns = _check(checks, "Default_DNS").members[0]
    assert isinstance(dns, SdwanHealthCheckMember)
    assert dns.interface == "wan1"
    assert dns.status == "up"
    assert dns.sla_met is True
    assert dns.latency_ms > 0
    assert dns.jitter_ms > 0
    assert dns.packet_loss_percent == 0.0
    # Counters are volatile between captures — assert shape, not values
    assert dns.packets_sent > 0
    assert dns.packets_received > 0
    assert dns.packets_received <= dns.packets_sent
    assert dns.state_changed > 0

    # The real edge case: member "up" while violating every SLA target
    fortiguard = _check(checks, "Default_FortiGuard").members[0]
    assert fortiguard.status == "up"
    assert fortiguard.packet_loss_percent == 50.0
    assert fortiguard.sla_met is False


def test_parse_health_check_empty_and_malformed() -> None:
    assert SdwanHealthCheck.list_from_api({"results": {}}) == []
    assert SdwanHealthCheck.list_from_api({"results": []}) == []
    assert SdwanHealthCheck.list_from_api({}) == []


def test_parse_health_check_member_defaults() -> None:
    checks = SdwanHealthCheck.list_from_api({"results": {"ping": {"wan2": {}}}})
    member = checks[0].members[0]
    assert member.status == ""
    assert member.sla_met is False
    assert member.latency_ms == 0.0
    assert member.packets_sent == 0


def test_parse_health_check_skips_non_dict_entries() -> None:
    checks = SdwanHealthCheck.list_from_api(
        {"results": {"ping": {"wan1": {}, "junk": "scalar"}, "bad": "scalar"}}
    )
    assert len(checks) == 1
    assert len(checks[0].members) == 1


def test_parse_sla_targets_non_list_tolerated() -> None:
    checks = SdwanHealthCheck.list_from_api(
        {"results": {"ping": {"wan1": {"sla_targets_met": "weird"}}}}
    )
    assert checks[0].members[0].sla_met is False


async def test_get_interfaces_real_shape(aresponses: ResponsesMockServer) -> None:
    """Parse the sanitized capture from a real v8.0.1 FortiGate."""
    aresponses.add(
        FAKE_HOST,
        f"/{EP_INTERFACES}",
        "GET",
        json_response(load_fixture("v8_0/system_interface.json")),
    )
    async with aiohttp.ClientSession() as session:
        interfaces = await make_client(session).get_interfaces()

    names = [i.name for i in interfaces]
    assert names == sorted(names)
    assert "wan1" in names
    assert "wan2" in names

    by_name = {i.name: i for i in interfaces}
    wan1 = by_name["wan1"]
    assert isinstance(wan1, InterfaceStatus)
    assert wan1.link is True
    assert wan1.speed_mbps == 1000.0
    assert wan1.prefix_len == 24
    assert wan1.alias == "UPLINK_ALIAS"
    assert wan1.mac == "02:00:00:00:00:01"
    assert wan1.tx_packets > 0
    assert wan1.rx_bytes > 0

    # Down interface: unconfigured addressing, zero speed
    wan2 = by_name["wan2"]
    assert wan2.link is False
    assert wan2.speed_mbps == 0.0
    assert wan2.ip == "0.0.0.0"
    assert wan2.prefix_len == 0


def test_parse_interfaces_empty_and_malformed() -> None:
    assert InterfaceStatus.list_from_api({"results": {}}) == []
    assert InterfaceStatus.list_from_api({"results": []}) == []
    assert InterfaceStatus.list_from_api({}) == []


def test_parse_interface_defaults_and_missing_name() -> None:
    interfaces = InterfaceStatus.list_from_api({"results": {"wan9": {}}})
    assert interfaces[0].name == "wan9"  # falls back to envelope key
    assert interfaces[0].link is False
    assert interfaces[0].ip == ""


async def test_wan_status_404_raises_not_found(aresponses: ResponsesMockServer) -> None:
    aresponses.add(FAKE_HOST, f"/{EP_SDWAN_HEALTH_CHECK}", "GET", aresponses.Response(status=404))
    async with aiohttp.ClientSession() as session:
        client = make_client(session)
        try:
            await client.get_wan_status()
        except FortiOSNotFoundError:
            pass
        else:
            raise AssertionError("expected FortiOSNotFoundError")


async def test_get_interface_roles_real_shape(aresponses: ResponsesMockServer) -> None:
    """Parse the sanitized CMDB capture from a real v8.0.1 FortiGate."""
    aresponses.add(
        FAKE_HOST,
        f"/{EP_CMDB_INTERFACES}",
        "GET",
        json_response(load_fixture("v8_0/system_interface_cmdb.json")),
    )
    async with aiohttp.ClientSession() as session:
        roles = await make_client(session).get_interface_roles()

    assert len(roles) == 20
    assert roles["wan1"] == "wan"
    assert roles["wan2"] == "wan"
    assert roles["dmz"] == "dmz"
    assert roles["internal"] == "lan"
    assert "virtual-wan-link" not in roles  # the SD-WAN zone is not a cmdb interface


async def test_interface_roles_defensive(aresponses: ResponsesMockServer) -> None:
    body = {
        "results": [
            {"name": "p1"},  # no role key -> ""
            {"name": "p2", "role": 7},  # non-string role -> ""
            "junk",  # non-dict entry -> skipped
            {"name": None, "role": "wan"},  # non-string name -> skipped
            {"name": "wan9", "role": "wan"},
        ]
    }
    aresponses.add(FAKE_HOST, f"/{EP_CMDB_INTERFACES}", "GET", json_response(body))
    async with aiohttp.ClientSession() as session:
        roles = await make_client(session).get_interface_roles()
    assert roles == {"p1": "", "p2": "", "wan9": "wan"}


async def test_interface_roles_non_list_results(aresponses: ResponsesMockServer) -> None:
    aresponses.add(FAKE_HOST, f"/{EP_CMDB_INTERFACES}", "GET", json_response({"results": {}}))
    async with aiohttp.ClientSession() as session:
        roles = await make_client(session).get_interface_roles()
    assert roles == {}


async def test_interface_roles_404_raises_not_found(
    aresponses: ResponsesMockServer,
) -> None:
    aresponses.add(FAKE_HOST, f"/{EP_CMDB_INTERFACES}", "GET", aresponses.Response(status=404))
    async with aiohttp.ClientSession() as session:
        client = make_client(session)
        try:
            await client.get_interface_roles()
        except FortiOSNotFoundError:
            pass
        else:
            raise AssertionError("expected FortiOSNotFoundError")
