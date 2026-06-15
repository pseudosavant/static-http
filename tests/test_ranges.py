from __future__ import annotations

import pytest

from http_here.ranges import RangeParseError, UnsatisfiableRangeError, parse_range_header


def test_parse_range_basic_start_end() -> None:
    assert parse_range_header("bytes=0-99", 1000) == (0, 99)


def test_parse_range_open_end() -> None:
    assert parse_range_header("bytes=100-", 1000) == (100, 999)


def test_parse_range_suffix() -> None:
    assert parse_range_header("bytes=-500", 1000) == (500, 999)


def test_parse_range_single_byte() -> None:
    assert parse_range_header("bytes=0-0", 5) == (0, 0)


def test_parse_range_clamps_past_eof() -> None:
    assert parse_range_header("bytes=1-50", 3) == (1, 2)


def test_parse_range_start_beyond_eof_unsatisfiable() -> None:
    with pytest.raises(UnsatisfiableRangeError):
        parse_range_header("bytes=1000-2000", 20)


def test_parse_range_empty_is_invalid() -> None:
    with pytest.raises(RangeParseError):
        parse_range_header("bytes=", 20)


def test_parse_range_non_byte_unit_invalid() -> None:
    with pytest.raises(RangeParseError):
        parse_range_header("items=0-10", 20)


def test_parse_range_multiple_ranges_rejected() -> None:
    with pytest.raises(RangeParseError):
        parse_range_header("bytes=0-1,2-3", 20)


def test_parse_range_suffix_zero_unsatisfiable() -> None:
    with pytest.raises(UnsatisfiableRangeError):
        parse_range_header("bytes=-0", 20)


def test_parse_range_malformed_numeric_values() -> None:
    with pytest.raises(RangeParseError):
        parse_range_header("bytes=abc-10", 20)
