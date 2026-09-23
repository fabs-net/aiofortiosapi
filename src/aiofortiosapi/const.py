"""Constants: endpoint paths and defaults.

WARNING: FortiOS monitor endpoint paths vary by firmware version and must be
verified against the target version's API reference (FNDN — Fortinet Developer
Network).  The paths below are known-good starting points for FortiOS 6.4 –
8.x (verified on v8.0.1); do NOT assume they exist on older or newer
firmware without checking.
"""

API_BASE = "api/v2"

EP_SYSTEM_STATUS = f"{API_BASE}/monitor/system/status"
EP_RESOURCE_USAGE = f"{API_BASE}/monitor/system/resource/usage"

# 7.0+: older firmware used monitor/user/device/select
EP_DETECTED_DEVICES = f"{API_BASE}/monitor/user/device/query"

# FortiOS 8.x: /monitor/license itself is a directory node that API tokens
# cannot read (403); the data lives one level deeper at license/status.
# Verified on v8.0.1; path unverified on 7.4/7.6 — probe with
# dev-scripts/version_check.py before relying on it there.
EP_LICENSE_STATUS = f"{API_BASE}/monitor/license/status"

# Future endpoints (add intentionally, verify paths per target version):
#   monitor/vpn/ipsec          — IPsec/VPN tunnel state
#   monitor/system/interface   — per-interface traffic stats
#   monitor/system/ha-statistics — HA cluster status

DEFAULT_PORT: int = 443
DEFAULT_TIMEOUT: float = 10.0

# Fallback window for deriving device online state: when an API response
# omits the is_online field, a device counts as online if it was last seen
# within this many seconds (mirrors HA device_tracker "consider_home").
DEFAULT_ONLINE_THRESHOLD: float = 300.0
