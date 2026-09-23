"""Tests for FortiOS version parsing."""

from __future__ import annotations

from aiofortiosapi import VersionInfo, parse_fortios_version


def test_full_form_with_build_and_maturity() -> None:
    assert parse_fortios_version("v7.6.7 build3704 (M)") == VersionInfo(7, 6, 7, 3704)


def test_plain_forms() -> None:
    assert parse_fortios_version("v8.0.1") == VersionInfo(8, 0, 1, 0)
    assert parse_fortios_version("8.0.1") == VersionInfo(8, 0, 1, 0)


def test_release_tuple_comparisons() -> None:
    assert parse_fortios_version("v7.4.9").release < (8, 0, 0)
    assert parse_fortios_version("v8.0.0").release >= (8, 0, 0)
    assert parse_fortios_version("v7.6.1").release >= (7, 6, 0)


def test_envelope_style_string() -> None:
    """The envelope reports e.g. 'v8.0.1' — build comes from elsewhere."""
    info = parse_fortios_version("v8.0.1")
    assert info.major == 8
    assert info.minor == 0
    assert info.patch == 1
    assert info.build == 0


def test_invalid_strings_return_none() -> None:
    assert parse_fortios_version("not a version") is None
    assert parse_fortios_version("") is None
    assert parse_fortios_version("vFortiOS") is None


def test_non_string_returns_none() -> None:
    """Defensive guard: firmware quirks can hand over non-string values."""
    assert parse_fortios_version(None) is None  # type: ignore[arg-type]
    assert parse_fortios_version(801) is None  # type: ignore[arg-type]
