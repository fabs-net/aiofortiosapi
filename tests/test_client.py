"""Tests for FortiOSClient request plumbing."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import aiohttp
import pytest
from aresponses import ResponsesMockServer

from aiofortiosapi import (
    FortiOSClient,
    FortiOSConnectionError,
    FortiOSNotFoundError,
    FortiOSResponseError,
)
from aiofortiosapi.client import _extract_error_detail
from aiofortiosapi.const import EP_DETECTED_DEVICES, EP_RESOURCE_USAGE, EP_SYSTEM_STATUS

from .conftest import FAKE_HOST, FAKE_TOKEN, json_response, load_fixture, make_client


@pytest.mark.asyncio
async def test_vdom_param_present_when_set(aresponses: ResponsesMockServer) -> None:
    received_qs: list[str] = []

    async def capture(request: aiohttp.web.Request) -> aiohttp.web.Response:
        received_qs.append(request.query_string)
        return json_response(load_fixture("system_status.json"))

    aresponses.add(FAKE_HOST, f"/{EP_SYSTEM_STATUS}", "GET", capture)
    async with aiohttp.ClientSession() as session:
        client = make_client(session, vdom="root")
        await client.get_system_status()

    assert "vdom=root" in received_qs[0]


@pytest.mark.asyncio
async def test_vdom_param_absent_when_none(aresponses: ResponsesMockServer) -> None:
    received_qs: list[str] = []

    async def capture(request: aiohttp.web.Request) -> aiohttp.web.Response:
        received_qs.append(request.query_string)
        return json_response(load_fixture("system_status.json"))

    aresponses.add(FAKE_HOST, f"/{EP_SYSTEM_STATUS}", "GET", capture)
    async with aiohttp.ClientSession() as session:
        client = make_client(session, vdom=None)
        await client.get_system_status()

    assert "vdom" not in received_qs[0]


@pytest.mark.asyncio
async def test_404_raises_not_found(aresponses: ResponsesMockServer) -> None:
    aresponses.add(FAKE_HOST, f"/{EP_SYSTEM_STATUS}", "GET", aresponses.Response(status=404))
    async with aiohttp.ClientSession() as session:
        client = make_client(session)
        with pytest.raises(FortiOSNotFoundError):
            await client.get_system_status()


@pytest.mark.asyncio
async def test_5xx_raises_response_error(aresponses: ResponsesMockServer) -> None:
    aresponses.add(
        FAKE_HOST, f"/{EP_SYSTEM_STATUS}", "GET", aresponses.Response(status=500, text="oops")
    )
    async with aiohttp.ClientSession() as session:
        client = make_client(session)
        with pytest.raises(FortiOSResponseError, match="oops"):
            await client.get_system_status()


@pytest.mark.asyncio
async def test_5xx_detail_uses_cli_error_key(aresponses: ResponsesMockServer) -> None:
    """FortiOS error envelopes carry the message in cli_error, not error."""
    body = json.dumps({"status": "error", "cli_error": "Permission denied."})
    aresponses.add(
        FAKE_HOST,
        f"/{EP_SYSTEM_STATUS}",
        "GET",
        aresponses.Response(status=502, text=body, content_type="application/json"),
    )
    async with aiohttp.ClientSession() as session:
        client = make_client(session)
        with pytest.raises(FortiOSResponseError, match="Permission denied."):
            await client.get_system_status()


def test_extract_error_detail_variants() -> None:
    assert _extract_error_detail('{"cli_error": "bad token"}') == "bad token"
    assert _extract_error_detail('{"message": "m", "error": "e"}') == "m"
    assert _extract_error_detail('{"error": "e"}') == "e"
    # Non-JSON and unrecognized shapes fall back to the raw body
    assert _extract_error_detail("<html>boom</html>") == "<html>boom</html>"
    assert _extract_error_detail('["unexpected"]') == '["unexpected"]'
    assert _extract_error_detail("x" * 500) == "x" * 200


@pytest.mark.asyncio
async def test_bad_json_raises_response_error(aresponses: ResponsesMockServer) -> None:
    aresponses.add(
        FAKE_HOST,
        f"/{EP_SYSTEM_STATUS}",
        "GET",
        aresponses.Response(text="not-json", content_type="application/json"),
    )
    async with aiohttp.ClientSession() as session:
        client = make_client(session)
        with pytest.raises(FortiOSResponseError):
            await client.get_system_status()


@pytest.mark.asyncio
async def test_timeout_raises_connection_error() -> None:
    # 192.0.2.1 is TEST-NET-1; unreachable by spec — a tiny timeout will always expire
    async with aiohttp.ClientSession() as session:
        client = FortiOSClient(
            host="192.0.2.1",
            token="tok",
            session=session,
            verify_ssl=False,
            request_timeout=0.001,
        )
        with pytest.raises(FortiOSConnectionError):
            await client.get_system_status()


@pytest.mark.asyncio
async def test_transport_error_raises_connection_error() -> None:
    """aiohttp.ClientError (DNS failure, connection reset, TLS) maps to FortiOSConnectionError."""
    session = MagicMock()
    session.request.return_value.__aenter__.side_effect = aiohttp.ClientError("connection reset")
    client = FortiOSClient(host=FAKE_HOST, token=FAKE_TOKEN, session=session)
    with pytest.raises(FortiOSConnectionError, match="connection reset"):
        await client.get_system_status()


@pytest.mark.asyncio
async def test_get_resource_usage(aresponses: ResponsesMockServer) -> None:
    aresponses.add(
        FAKE_HOST,
        f"/{EP_RESOURCE_USAGE}",
        "GET",
        json_response(load_fixture("resource_usage.json")),
    )
    async with aiohttp.ClientSession() as session:
        usage = await make_client(session).get_resource_usage()
    assert usage.cpu_percent == 0.0
    assert usage.memory_percent == 34.0
    assert usage.sessions == 279 + 57
    assert usage.session_setup_rate == 7


@pytest.mark.asyncio
async def test_get_returns_raw_envelope(aresponses: ResponsesMockServer) -> None:
    """get() bypasses the typed models and returns the full JSON envelope."""
    aresponses.add(
        FAKE_HOST,
        "/monitor/system/ha-statistics",
        "GET",
        json_response(load_fixture("system_status.json")),
    )
    async with aiohttp.ClientSession() as session:
        raw = await make_client(session).get("monitor/system/ha-statistics")
    assert raw["version"] == "v7.6.1"
    assert raw["results"]["Hostname"] == "homelab-fw"


@pytest.mark.asyncio
async def test_get_detected_devices(aresponses: ResponsesMockServer) -> None:
    aresponses.add(
        FAKE_HOST,
        f"/{EP_DETECTED_DEVICES}",
        "GET",
        json_response(load_fixture("detected_devices.json")),
    )
    async with aiohttp.ClientSession() as session:
        devices = await make_client(session).get_detected_devices()
    assert len(devices) == 2
    assert devices[0].mac == "aa:bb:cc:dd:ee:01"
    assert devices[0].is_online is True
    assert devices[1].is_online is False


@pytest.mark.asyncio
async def test_get_detected_devices_falls_back_to_last_seen_freshness(
    aresponses: ResponsesMockServer,
) -> None:
    """Without an is_online field, freshness decides; the client threshold applies."""
    body = {"results": [{"mac": "aa", "last_seen": 1750000000}]}
    for _ in range(2):
        aresponses.add(FAKE_HOST, f"/{EP_DETECTED_DEVICES}", "GET", json_response(body))

    async with aiohttp.ClientSession() as session:
        # Fixture timestamps are far in the past: default 300s window => offline
        stale = await make_client(session).get_detected_devices()
        # Effectively infinite window overrides staleness
        generous = await make_client(session, device_online_threshold=1e12).get_detected_devices()

    assert all(d.is_online is False for d in stale)
    assert all(d.is_online is True for d in generous)


@pytest.mark.asyncio
async def test_verify_ssl_false_does_not_raise(aresponses: ResponsesMockServer) -> None:
    aresponses.add(
        FAKE_HOST,
        f"/{EP_SYSTEM_STATUS}",
        "GET",
        json_response(load_fixture("system_status.json")),
    )
    async with aiohttp.ClientSession() as session:
        client = make_client(session)  # make_client defaults to verify_ssl=False
        status = await client.get_system_status()
    assert status.hostname == "homelab-fw"
