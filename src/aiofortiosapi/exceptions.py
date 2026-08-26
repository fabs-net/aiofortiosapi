"""Exception hierarchy for aiofortiosapi.

Map to Home Assistant config entry states:
  FortiOSConnectionError      -> ConfigEntryNotReady  (retry)
  FortiOSAuthenticationError  -> ConfigEntryAuthFailed (reauth)
  FortiOSNotFoundError        -> inspect / log
  FortiOSResponseError        -> log / raise
"""


class FortiOSError(Exception):
    """Base exception for all aiofortiosapi errors."""


class FortiOSConnectionError(FortiOSError):
    """Transport-level or timeout failure.

    Raised for aiohttp.ClientError and asyncio.TimeoutError.
    Home Assistant should map this to ConfigEntryNotReady.
    """


class FortiOSAuthenticationError(FortiOSError):
    """HTTP 401 or 403 response.

    Home Assistant should map this to ConfigEntryAuthFailed.
    """


class FortiOSNotFoundError(FortiOSError):
    """HTTP 404 response — endpoint does not exist on this FortiOS version."""


class FortiOSResponseError(FortiOSError):
    """Unexpected or unparseable response (bad JSON, 5xx, other 4xx)."""
