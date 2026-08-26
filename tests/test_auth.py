"""Tests for authentication behaviour."""

from __future__ import annotations

import aiohttp
import pytest
from aresponses import ResponsesMockServer

from aiofortiosapi import FortiOSAuthenticationError
from aiofortiosapi.const import EP_SYSTEM_STATUS

from .conftest import FAKE_HOST, FAKE_TOKEN, json_response, load_fixture, make_client


@pytest.mark.asyncio
async def test_401_raises_auth_error(aresponses: ResponsesMockServer) -> None:
    aresponses.add(FAKE_HOST, f"/{EP_SYSTEM_STATUS}", "GET", aresponses.Response(status=401))
    async with aiohttp.ClientSession() as session:
        client = make_client(session)
        with pytest.raises(FortiOSAuthenticationError):
            await client.get_system_status()


@pytest.mark.asyncio
async def test_403_raises_auth_error(aresponses: ResponsesMockServer) -> None:
    aresponses.add(FAKE_HOST, f"/{EP_SYSTEM_STATUS}", "GET", aresponses.Response(status=403))
    async with aiohttp.ClientSession() as session:
        client = make_client(session)
        with pytest.raises(FortiOSAuthenticationError):
            await client.get_system_status()


@pytest.mark.asyncio
async def test_valid_token_succeeds(aresponses: ResponsesMockServer) -> None:
    aresponses.add(
        FAKE_HOST,
        f"/{EP_SYSTEM_STATUS}",
        "GET",
        json_response(load_fixture("system_status.json")),
    )
    async with aiohttp.ClientSession() as session:
        client = make_client(session)
        status = await client.get_system_status()
    assert status.serial == "FGT60FXXXXXXXX"


@pytest.mark.asyncio
async def test_bearer_token_in_header(aresponses: ResponsesMockServer) -> None:
    """Token must be sent as Authorization: Bearer, never in the URL."""
    received_auth: list[str] = []
    received_url: list[str] = []

    async def capture(request: aiohttp.web.Request) -> aiohttp.web.Response:
        received_auth.append(request.headers.get("Authorization", ""))
        received_url.append(str(request.url))
        return json_response(load_fixture("system_status.json"))

    aresponses.add(FAKE_HOST, f"/{EP_SYSTEM_STATUS}", "GET", capture)
    async with aiohttp.ClientSession() as session:
        client = make_client(session)
        await client.get_system_status()

    assert received_auth[0] == f"Bearer {FAKE_TOKEN}"
    assert "access_token" not in received_url[0]


@pytest.mark.asyncio
async def test_async_validate_propagates_auth_error(aresponses: ResponsesMockServer) -> None:
    aresponses.add(FAKE_HOST, f"/{EP_SYSTEM_STATUS}", "GET", aresponses.Response(status=401))
    async with aiohttp.ClientSession() as session:
        client = make_client(session)
        with pytest.raises(FortiOSAuthenticationError):
            await client.async_validate()
