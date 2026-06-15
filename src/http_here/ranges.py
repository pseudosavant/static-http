"""Range header parsing helpers for HTTP byte-range handling."""

from __future__ import annotations

class RangeParseError(ValueError):
    """Raised when a byte range header is malformed."""


class UnsatisfiableRangeError(ValueError):
    """Raised when a syntactically valid range is outside the file bounds."""


def _parse_non_negative_int(raw: str) -> int:
    if raw == "":
        raise RangeParseError("Malformed range value")
    if not raw.isdigit():
        raise RangeParseError("Malformed range value")
    return int(raw)


def parse_range_header(range_header: str, total_size: int) -> tuple[int, int] | None:
    """Parse a single-byte-range header and return an inclusive byte interval.

    Args:
        range_header: Raw Range header value, typically ``bytes=start-end``.
        total_size: Total size of the target file.

    Returns:
        A ``(start, end)`` tuple if a valid single range was supplied.
        ``None`` when no range was supplied.

    Raises:
        RangeParseError: for invalid syntax.
        UnsatisfiableRangeError: for syntactically valid but unsatisfiable ranges.
    """

    if not range_header:
        return None

    if not range_header.startswith("bytes="):
        raise RangeParseError("Only byte ranges are supported")

    spec = range_header[6:].strip()
    if not spec:
        raise RangeParseError("Empty Range header")
    if "," in spec:
        raise RangeParseError("Multiple ranges are not supported in v1")

    if spec.count("-") != 1:
        raise RangeParseError("Malformed range value")

    start_text, end_text = spec.split("-", 1)
    start_text = start_text.strip()
    end_text = end_text.strip()

    if total_size < 0:
        raise RangeParseError("Invalid file size")

    if start_text and end_text:
        start = _parse_non_negative_int(start_text)
        end = _parse_non_negative_int(end_text)
        if start > end:
            raise RangeParseError("Malformed range value")
        if total_size == 0 or start >= total_size:
            raise UnsatisfiableRangeError("Range outside file size")
        return start, min(end, total_size - 1)

    if start_text:
        start = _parse_non_negative_int(start_text)
        if start < 0:
            raise RangeParseError("Malformed range value")
        if total_size == 0 or start >= total_size:
            raise UnsatisfiableRangeError("Range outside file size")
        return start, total_size - 1

    if not end_text:
        raise RangeParseError("Malformed range value")

    suffix = _parse_non_negative_int(end_text)
    if suffix <= 0:
        raise UnsatisfiableRangeError("Range outside file size")
    if total_size == 0:
        raise UnsatisfiableRangeError("Range outside file size")
    return max(total_size - suffix, 0), total_size - 1


def content_range(start: int, end: int, total_size: int) -> str:
    return f"bytes {start}-{end}/{total_size}"


def unsatisfiable_content_range(total_size: int) -> str:
    return f"bytes */{total_size}"
