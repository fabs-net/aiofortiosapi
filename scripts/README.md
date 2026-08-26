# FortiOS connectivity checker

A small CLI script that verifies a `aiofortiosapi` client against a real
FortiGate. It reads the connection settings from a YAML file and exercises the
three monitor endpoints (`system/status`, `system/resource/usage`,
`user/device/query`), printing the results. Handy for confirming a newly
generated REST API token works before wiring it into Home Assistant.

## Requirements (Linux box)

```bash
python3 -m venv venv
source venv/bin/activate
pip install aiofortiosapi pyyaml
```

## Configure

```bash
cp config.example.yaml config.yaml
# edit config.yaml with your host / port / token / vdom
```

## Run

```bash
python3 check_fortios.py            # reads ./config.yaml
python3 check_fortios.py other.yaml # or a specific file
```

Exit code is `0` on success, `1` on any failure. Friendly messages distinguish
auth failures (bad token / untrusted host), connectivity failures, and
unsupported endpoints.
