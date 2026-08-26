"""Shared pytest fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiohttp
from aresponses import ResponsesMockServer

from aiofortiosapi import FortiOSClient

FIXTURES_DIR = Path(__file__).parent / "fixtures"
FAKE_HOST = "fortigate.local"
FAKE_TOKEN = "test-token-abc123"


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES_DIR / name).read_text())


def json_response(data: dict[str, Any], status: int = 200) -> Any:
    """Build an aresponses-compatible JSON response (v3 API)."""
    return ResponsesMockServer.Response(
        text=json.dumps(data),
        status=status,
        content_type="application/json",
    )


def make_client(session: aiohttp.ClientSession, **kwargs: Any) -> FortiOSClient:
    return FortiOSClient(
        host=FAKE_HOST,
        token=FAKE_TOKEN,
        session=session,
        verify_ssl=False,
        **kwargs,
    )
