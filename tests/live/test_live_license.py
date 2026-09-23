"""Live tests for license status against a real FortiGate (env-gated)."""

from __future__ import annotations

import pytest

from aiofortiosapi import LicenseFeature, LicenseStatus

pytestmark = pytest.mark.live


async def test_license_status(live_client) -> None:
    status = await live_client.get_license_status()
    assert isinstance(status, LicenseStatus)
    assert status.forticare.status  # non-empty on real firmware
    assert len(status.features) >= 10
    assert all(isinstance(f, LicenseFeature) for f in status.features)
    assert all(f.name for f in status.features)
