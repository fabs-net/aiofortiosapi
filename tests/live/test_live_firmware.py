"""Live tests for firmware status against a real FortiGate (env-gated)."""

from __future__ import annotations

import pytest

from aiofortiosapi import FirmwareImage, FirmwareStatus

pytestmark = pytest.mark.live


async def test_firmware_status(live_client) -> None:
    status = await live_client.get_firmware_status()
    assert isinstance(status, FirmwareStatus)
    assert status.current.version  # non-empty on real firmware
    assert isinstance(status.available, list)
    assert all(isinstance(img, FirmwareImage) for img in status.available)
