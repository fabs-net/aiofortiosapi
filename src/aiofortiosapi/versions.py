"""Parse and compare FortiOS version strings.

FortiOS reports versions in several shapes depending on context, e.g.
``"v8.0.1"``, ``"8.0.1"``, or ``"v7.6.7 build3704 (M)"``.  The helper here
extracts the numeric components so callers can do range checks without a
third-party dependency (the library keeps aiohttp as its only runtime dep).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_VERSION_RE = re.compile(r"v?(\d+)\.(\d+)\.(\d+)(?:\s+build(\d+))?")


@dataclass(frozen=True, slots=True)
class VersionInfo:
    """Numeric FortiOS version, tuple-comparable via ``release``.

    ``VersionInfo(8, 0, 1) >= (7, 6, 0)`` works through the ``release``
    property; ``build`` distinguishes patches of the same release but is not
    part of release comparisons.
    """

    major: int
    minor: int
    patch: int
    build: int

    @property
    def release(self) -> tuple[int, int, int]:
        """Return the (major, minor, patch) tuple for comparisons."""
        return (self.major, self.minor, self.patch)


def parse_fortios_version(raw: str) -> VersionInfo | None:
    """Extract numeric version components from a FortiOS version string.

    Returns ``None`` for anything that does not match ``v?MAJOR.MINOR.PATCH``
    (optionally followed by ``buildN``).  Callers treat ``None`` as
    "unknown version" and fall back to capability detection.
    """
    if not isinstance(raw, str):
        return None
    match = _VERSION_RE.search(raw)
    if match is None:
        return None
    major, minor, patch, build = match.groups()
    return VersionInfo(
        major=int(major),
        minor=int(minor),
        patch=int(patch),
        build=int(build) if build else 0,
    )
