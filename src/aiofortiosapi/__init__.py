"""aiofortiosapi — async FortiOS REST API client for Home Assistant."""

from .client import FortiOSClient
from .const import DEFAULT_ONLINE_THRESHOLD
from .exceptions import (
    FortiOSAuthenticationError,
    FortiOSConnectionError,
    FortiOSError,
    FortiOSNotFoundError,
    FortiOSResponseError,
)
from .models import (
    DetectedDevice,
    FortiCareRegistration,
    FortiCareSupport,
    FortiGuardConnection,
    LicenseFeature,
    LicenseStatus,
    ResourceUsage,
    SystemStatus,
)
from .versions import VersionInfo, parse_fortios_version

__version__ = "0.1.0"

__all__ = [
    "FortiOSClient",
    # exceptions
    "FortiOSError",
    "FortiOSConnectionError",
    "FortiOSAuthenticationError",
    "FortiOSNotFoundError",
    "FortiOSResponseError",
    # models
    "SystemStatus",
    "ResourceUsage",
    "DetectedDevice",
    "LicenseFeature",
    "LicenseStatus",
    "FortiGuardConnection",
    "FortiCareRegistration",
    "FortiCareSupport",
    # versions
    "VersionInfo",
    "parse_fortios_version",
    # constants
    "DEFAULT_ONLINE_THRESHOLD",
    "__version__",
]
