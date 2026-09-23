# aiofortiosapi

Async Python client for the FortiOS REST API, built for the [Home Assistant](https://www.home-assistant.io/) `fortios` integration.

> **Community project** — not affiliated with or supported by Fortinet TAC.

## Install

```bash
pip install aiofortiosapi
```

## Usage

The library requires an injected `aiohttp.ClientSession` — Home Assistant provides one via
`async_get_clientsession(hass)`. You own the session lifecycle; this library never creates or closes it.

```python
import asyncio
import aiohttp
from aiofortiosapi import FortiOSClient, FortiOSAuthenticationError, FortiOSConnectionError

async def main() -> None:
    session = aiohttp.ClientSession()
    try:
        client = FortiOSClient(
            host="192.168.1.1",
            token="your-rest-api-token",
            session=session,
            verify_ssl=False,   # set True in production with a valid cert
        )
        status = await client.get_system_status()
        print(status.hostname, status.version)

        usage = await client.get_resource_usage()
        print(f"CPU {usage.cpu_percent}%  MEM {usage.memory_percent}%")

        devices = await client.get_detected_devices()
        for d in devices:
            print(d.mac, d.hostname, d.ip, "online" if d.is_online else "offline")

        licenses = await client.get_license_status()
        print("FortiCare:", licenses.forticare.status)
        print("FortiGuard:", "connected" if licenses.fortiguard.connected else "down")
        for feature in licenses.features:
            if feature.is_licensed:
                print("licensed:", feature.name, feature.version)

        firmware = await client.get_firmware_status()
        print("running:", firmware.current.version)
        print("update available:", firmware.update_available)

        for check in await client.get_wan_status():
            for member in check.members:
                print(
                    check.name, member.interface, member.status,
                    f"{member.latency_ms:.0f}ms", f"loss {member.packet_loss_percent}%",
                    "SLA ok" if member.sla_met else "SLA violated",
                )

        for iface in await client.get_interfaces():
            if iface.link:
                print(iface.name, iface.ip, f"{iface.speed_mbps:.0f} Mbps")
    except FortiOSAuthenticationError:
        print("Bad token — re-enter credentials")
    except FortiOSConnectionError:
        print("Cannot reach the FortiGate — check host/port")
    finally:
        await session.close()

asyncio.run(main())
```

## Generating a FortiOS REST API token

1. In the FortiGate GUI go to **System → Administrators → Create New → REST API Admin**.
2. Set a **Trusted Host** (the IP of your Home Assistant instance) to restrict token use.
3. Assign a read-only profile (`prof_admin` or custom).
4. Copy the generated token — it is shown only once.

The library uses `Authorization: Bearer <token>` (not the legacy `?access_token=` query string).

### Device online state

`DetectedDevice.is_online` uses the flag reported by FortiOS. On firmware that
omits the field, it falls back to deriving online state from `last_seen`
freshness: a device counts as online when seen within
`DEFAULT_ONLINE_THRESHOLD` seconds (300). Tune the fallback per client:

```python
client = FortiOSClient(..., device_online_threshold=600)
```

## Scope

`aiofortiosapi` is intentionally minimal:

- **Three typed monitor endpoints** (`get_system_status`, `get_resource_usage`,
  `get_detected_devices`) used by the Home Assistant integration.
- `get_license_status()` — FortiCare registration, FortiGuard connectivity and
  per-feature entitlements (antivirus, IPS, app-control, cloud services, …)
  with a derived `is_licensed` flag (`licensed` or `free_license`).
- `get_firmware_status()` — running firmware image plus the FortiGuard image
  catalog, with a derived `update_available` flag.
- `get_wan_status()` — SD-WAN health-check results per check and member
  interface: latency, jitter, packet loss, bandwidth counters, and a derived
  `sla_met` flag that can legitimately diverge from the link status.
- `get_interfaces()` — per-interface link state, addressing and traffic
  counters.
- `parse_fortios_version()` — dependency-free version parsing for range checks.
- A generic `get(path)` for any other endpoint that returns the raw JSON envelope.
- **No** config-write, CMDB, file upload, SSH fallback, or CLI helpers.
- **No** session/cookie login flow — Bearer token only.

This keeps the dependency tree small (runtime dep: `aiohttp` only) and passes HA integration
quality review requirements.

### Firmware compatibility

Endpoint paths vary slightly across FortiOS versions. All models parse
defensively: fields a firmware does not report default to `""`/`0` instead of
raising, and endpoints missing on a version raise `FortiOSNotFoundError` so
callers can disable just that feature.

Note for the license endpoint (verified on v8.0.1): `/monitor/license` itself
is a directory node that API tokens cannot read (403) — the data lives at
`monitor/license/status`. On 7.4/7.6 this path is unverified; probe a device
before relying on it there.

## Testing

CI runs the unit suite with mocked HTTP responses (`aresponses`) — no
FortiGate required.

Fixtures under `tests/fixtures/v8_0/` are sanitized captures from real
hardware (FortiOS v8.0.1), so unit tests exercise actual firmware response
shapes instead of invented JSON. Sensitive values (serial, account, company,
public IPs, server addresses) are replaced; capture more firmware versions
by pointing a capture script at a device and adding a new version directory.

### Live tests (optional, opt-in)

`tests/live/` runs selected tests against a real FortiGate. They self-skip
unless credentials are present in the environment or a gitignored `.env`
at the repo root:

```
FGT_HOST=192.168.1.1
FGT_TOKEN=<read-only REST API token>
FGT_PORT=443      # optional, custom admin HTTPS port
FGT_VDOM=root     # optional
FGT_VERIFY_SSL=0  # optional, 1 to verify TLS certs
```

Run with:

```bash
pytest -m live
```

CI never sets these variables, so live tests never run there.

## Exception hierarchy

| Exception | When raised | HA mapping |
|---|---|---|
| `FortiOSConnectionError` | Transport/timeout failure | `ConfigEntryNotReady` |
| `FortiOSAuthenticationError` | HTTP 401 / 403 | `ConfigEntryAuthFailed` |
| `FortiOSNotFoundError` | HTTP 404 | log / inspect |
| `FortiOSResponseError` | Bad JSON, 5xx, other 4xx | log / raise |

## License

MIT
