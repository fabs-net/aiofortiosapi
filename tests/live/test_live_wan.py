"""Live tests for SD-WAN health and interface status (env-gated)."""

from __future__ import annotations

import pytest

from aiofortiosapi import InterfaceStatus, SdwanHealthCheck

pytestmark = pytest.mark.live


async def test_wan_status(live_client) -> None:
    checks = await live_client.get_wan_status()
    assert all(isinstance(c, SdwanHealthCheck) for c in checks)
    for check in checks:
        assert check.name
        for member in check.members:
            assert member.interface
            assert member.latency_ms >= 0


async def test_interfaces(live_client) -> None:
    interfaces = await live_client.get_interfaces()
    assert len(interfaces) >= 2
    assert all(isinstance(i, InterfaceStatus) for i in interfaces)
    names = [i.name for i in interfaces]
    assert names == sorted(names)
    assert any(i.link for i in interfaces)
