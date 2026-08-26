#!/usr/bin/env python3
"""Quick connectivity check for a FortiGate using the aiofortiosapi client.

Reads connection settings from a YAML file and exercises the three monitor
endpoints, printing the results.  Useful for verifying that a freshly created
REST API token works before wiring it up in Home Assistant.

Usage:
    python3 check_fortios.py [config.yaml]

The config file defaults to ``config.yaml``.  See ``config.example.yaml``.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

import aiohttp
import yaml

from aiofortiosapi import (
    FortiOSAuthenticationError,
    FortiOSClient,
    FortiOSConnectionError,
    FortiOSNotFoundError,
    FortiOSResponseError,
)

DEFAULT_CONFIG = "config.yaml"


def load_config(path: Path) -> dict[str, Any]:
    """Load and validate the YAML config file."""
    if not path.exists():
        sys.exit(f"Config file not found: {path}")
    try:
        data: Any = yaml.safe_load(path.read_text())
    except yaml.YAMLError as err:
        sys.exit(f"Invalid YAML in {path}: {err}")

    if not isinstance(data, dict):
        sys.exit("Config must be a YAML mapping with at least 'host' and 'token'.")

    host = data.get("host")
    token = data.get("token")
    if not host or not token:
        sys.exit("Config must define 'host' and 'token'.")
    return data


async def check(client: FortiOSClient) -> None:
    """Run the checks and print results on success; raise on failure."""
    status = await client.get_system_status()
    print(f"System status     : {status.hostname or '<no hostname>'}")
    print(f"  version         : {status.version}")
    print(f"  serial          : {status.serial}")
    print(f"  model           : {status.model}")

    usage = await client.get_resource_usage()
    print(
        f"Resource usage    : CPU {usage.cpu_percent:.0f}%  "
        f"Mem {usage.memory_percent:.0f}%  Sessions {usage.sessions}  "
        f"Setup rate {usage.session_setup_rate}/s"
    )

    devices = await client.get_detected_devices()
    online = sum(1 for d in devices if d.is_online)
    print(f"Detected devices  : {len(devices)} total, {online} online")
    for d in devices[:10]:
        state = "online" if d.is_online else "offline"
        print(f"  - {d.hostname or '<unknown>':<20} {d.mac:<19} {d.ip:<15} {state}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check FortiOS connectivity.")
    parser.add_argument(
        "config",
        nargs="?",
        default=DEFAULT_CONFIG,
        help="Path to the YAML config file (default: config.yaml).",
    )
    return parser.parse_args(argv)


async def async_main(cfg: dict[str, Any]) -> None:
    async with aiohttp.ClientSession() as session:
        client = FortiOSClient(
            session=session,
            host=cfg["host"],
            port=cfg.get("port", 443),
            token=cfg["token"],
            vdom=cfg.get("vdom"),
            verify_ssl=bool(cfg.get("verify_ssl", False)),
            request_timeout=float(cfg.get("timeout", 10)),
        )
        await check(client)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    cfg = load_config(Path(args.config))

    print(f"Checking FortiGate at {cfg['host']}:{cfg.get('port', 443)} ...")
    try:
        asyncio.run(async_main(cfg))
    except FortiOSAuthenticationError:
        print(
            "FAILED: Invalid authentication (bad token or untrusted host) - "
            "check the token and Trusted Host setting."
        )
        return 1
    except FortiOSConnectionError as err:
        print(f"FAILED: Cannot reach the FortiGate - check host/port/network. ({err})")
        return 1
    except FortiOSNotFoundError as err:
        print(f"FAILED: Endpoint not found on this FortiOS firmware. ({err})")
        return 1
    except FortiOSResponseError as err:
        print(f"FAILED: Unexpected API response. ({err})")
        return 1
    except Exception as err:  # noqa: BLE001 - top-level CLI boundary
        print(f"FAILED: Unexpected error. ({err})")
        return 1

    print("SUCCESS: Connection and all endpoints work.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
