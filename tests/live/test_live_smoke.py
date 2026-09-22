"""Live smoke tests against a real FortiGate (env-gated, never run in CI)."""

from __future__ import annotations

import pytest

from aiofortiosapi import ResourceUsage, SystemStatus

pytestmark = pytest.mark.live


async def test_system_status(live_client) -> None:
    status = await live_client.get_system_status()
    assert isinstance(status, SystemStatus)
    assert status.hostname
    assert status.version


async def test_resource_usage(live_client) -> None:
    usage = await live_client.get_resource_usage()
    assert isinstance(usage, ResourceUsage)
    assert usage.cpu_percent >= 0
    assert usage.memory_percent >= 0
    assert usage.sessions >= 0
