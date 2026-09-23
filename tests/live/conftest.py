"""Fixtures for live tests against a real FortiGate.

Live tests opt in via ``@pytest.mark.live`` and the ``live_client`` fixture.
They self-skip unless ``FGT_HOST`` and ``FGT_TOKEN`` are set in the
environment; CI never sets them, so normal runs and CI are unaffected.

For local runs the gitignored ``.env`` at the repo root is honoured:

    FGT_HOST=192.168.1.1
    FGT_TOKEN=<read-only REST API token>
    FGT_PORT=8443              # optional, custom admin HTTPS port (default 443)
    FGT_VDOM=root              # optional
    FGT_VERIFY_SSL=0           # optional, 1 to verify TLS certs

Run with:  pytest -m live
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import aiohttp
import pytest

from aiofortiosapi import FortiOSClient
from aiofortiosapi.const import DEFAULT_PORT


def _load_dotenv() -> None:
    """Populate os.environ from the repo-root .env without overriding it."""
    env_path = Path(__file__).parents[2] / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

FGT_HOST = os.environ.get("FGT_HOST")
FGT_TOKEN = os.environ.get("FGT_TOKEN")


def _env_port() -> int:
    try:
        return int(os.environ.get("FGT_PORT", ""))
    except ValueError:
        return DEFAULT_PORT


@pytest.fixture
async def live_client() -> AsyncIterator[FortiOSClient]:
    """A FortiOSClient aimed at the real FortiGate described by the env."""
    if not FGT_HOST or not FGT_TOKEN:
        pytest.skip("FGT_HOST/FGT_TOKEN not set; live tests need a real FortiGate")
    async with aiohttp.ClientSession() as session:
        yield FortiOSClient(
            host=FGT_HOST,
            token=FGT_TOKEN,
            session=session,
            port=_env_port(),
            verify_ssl=os.environ.get("FGT_VERIFY_SSL", "0") in ("1", "true", "yes"),
            vdom=os.environ.get("FGT_VDOM") or None,
        )
