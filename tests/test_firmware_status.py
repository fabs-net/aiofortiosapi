"""Tests for firmware status parsing and client wiring."""

from __future__ import annotations

import aiohttp
from aresponses import ResponsesMockServer

from aiofortiosapi import FirmwareImage, FirmwareStatus, FortiOSNotFoundError
from aiofortiosapi.const import EP_FIRMWARE

from .conftest import FAKE_HOST, json_response, load_fixture, make_client

AVAILABLE_COUNT = 90  # captured from a real v8.0.1 FortiGuard catalog


def _image(raw: dict) -> FirmwareImage:
    return FirmwareImage.from_api(raw)


async def test_get_firmware_status_real_shape(aresponses: ResponsesMockServer) -> None:
    """Parse the sanitized capture from a real v8.0.1 FortiGate."""
    aresponses.add(
        FAKE_HOST,
        f"/{EP_FIRMWARE}",
        "GET",
        json_response(load_fixture("v8_0/system_firmware.json")),
    )
    async with aiohttp.ClientSession() as session:
        status = await make_client(session).get_firmware_status()

    assert isinstance(status, FirmwareStatus)
    current = status.current
    assert current.version == "v8.0.1"
    assert (current.major, current.minor, current.patch) == (8, 0, 1)
    assert current.build == 245
    assert current.release_type == "GA"
    assert current.source == "current"

    assert len(status.available) == AVAILABLE_COUNT
    assert all(img.source == "fortiguard" for img in status.available)
    # The captured catalog offers no image newer than the running one
    assert status.update_available is False


def test_parse_current_image_missing_fields() -> None:
    status = FirmwareStatus.from_api({"results": {"current": {"version": "v7.6.7"}}})
    assert status.current.version == "v7.6.7"
    assert status.current.build == 0
    assert status.current.image_id == ""


def test_parse_update_available_true() -> None:
    raw = {
        "results": {
            "current": {"version": "v8.0.1", "major": 8, "minor": 0, "patch": 1},
            "available": [
                {"version": "v8.0.2", "major": 8, "minor": 0, "patch": 2},
                {"version": "v8.0.0", "major": 8, "minor": 0, "patch": 0},
            ],
        }
    }
    status = FirmwareStatus.from_api(raw)
    assert status.update_available is True


def test_parse_update_available_false_on_downgrades_only() -> None:
    raw = {
        "results": {
            "current": {"version": "v8.0.1", "major": 8, "minor": 0, "patch": 1},
            "available": [
                {"version": "v8.0.0", "major": 8, "minor": 0, "patch": 0},
                {"version": "v7.6.7", "major": 7, "minor": 6, "patch": 7},
            ],
        }
    }
    assert FirmwareStatus.from_api(raw).update_available is False


def test_parse_empty_and_malformed_results() -> None:
    assert FirmwareStatus.from_api({"results": {}}).available == []
    assert FirmwareStatus.from_api({"results": []}).available == []
    assert FirmwareStatus.from_api({}).update_available is False


def test_parse_skips_non_dict_available_entries() -> None:
    raw = {"results": {"current": {}, "available": [{"version": "v9.0.0"}, "junk"]}}
    status = FirmwareStatus.from_api(raw)
    assert len(status.available) == 1
    # available (9.0.0) newer than defaulted current (0, 0, 0)
    assert status.update_available is True


def test_release_tuple_comparison() -> None:
    image = _image({"major": 7, "minor": 6, "patch": 7, "build": 3704})
    assert image.release < (8, 0, 0)
    assert image.build == 3704


async def test_firmware_404_raises_not_found(aresponses: ResponsesMockServer) -> None:
    aresponses.add(FAKE_HOST, f"/{EP_FIRMWARE}", "GET", aresponses.Response(status=404))
    async with aiohttp.ClientSession() as session:
        client = make_client(session)
        try:
            await client.get_firmware_status()
        except FortiOSNotFoundError:
            pass
        else:
            raise AssertionError("expected FortiOSNotFoundError")
