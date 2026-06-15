from __future__ import annotations

import io
import re
from collections import namedtuple

import pytest

from http_here import qrcode


class _TtyStringIO(io.StringIO):
    def isatty(self) -> bool:
        return True


_FORMAT_MASK_BY_BITS = {
    int("111011111000100", 2): 0,
    int("111001011110011", 2): 1,
    int("111110110101010", 2): 2,
    int("111100010011101", 2): 3,
    int("110011000101111", 2): 4,
    int("110001100011000", 2): 5,
    int("110110001000001", 2): 6,
    int("110100101110110", 2): 7,
}
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _wide_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_size = namedtuple("Size", "columns lines")(120, 40)
    monkeypatch.setattr(qrcode.shutil, "get_terminal_size", lambda fallback=(80, 24): fake_size)


def _parse_plain_rendered_matrix(rendered: str) -> list[list[bool]]:
    qr_lines = rendered.splitlines()[:-1]
    size = len(qr_lines) - 8
    assert size > 0

    matrix = []
    for line in qr_lines[4 : 4 + size]:
        cells = [line[i : i + 2] for i in range(0, len(line), 2)]
        assert len(cells) >= size + 8
        matrix.append([cell != "  " for cell in cells[4 : 4 + size]])
    return matrix


def _parse_ansi_cells(line: str) -> list[bool]:
    cells = []
    dark = False
    space_count = 0
    index = 0

    while index < len(line):
        match = _ANSI_RE.match(line, index)
        if match:
            sequence = match.group(0)
            if sequence == "\x1b[40m":
                dark = True
            elif sequence in {"\x1b[107m", "\x1b[0m"}:
                dark = False
            index = match.end()
            continue

        assert line[index] == " "
        space_count += 1
        if space_count == 2:
            cells.append(dark)
            space_count = 0
        index += 1

    assert space_count == 0
    return cells


def _parse_ansi_rendered_matrix(rendered: str) -> list[list[bool]]:
    qr_lines = rendered.splitlines()[:-1]
    size = len(qr_lines) - 8
    assert size > 0

    matrix = []
    for line in qr_lines[4 : 4 + size]:
        cells = _parse_ansi_cells(line)
        assert len(cells) >= size + 8
        matrix.append(cells[4 : 4 + size])
    return matrix


def _mark_function_modules(size: int) -> list[list[bool]]:
    version = (size - 17) // 4
    function = [[False for _ in range(size)] for _ in range(size)]

    def mark(row: int, col: int) -> None:
        if 0 <= row < size and 0 <= col < size:
            function[row][col] = True

    def mark_finder(top: int, left: int) -> None:
        for row in range(top - 1, top + 8):
            for col in range(left - 1, left + 8):
                mark(row, col)

    mark_finder(0, 0)
    mark_finder(0, size - 7)
    mark_finder(size - 7, 0)

    if version > 1:
        center = size - 7
        for row in range(center - 2, center + 3):
            for col in range(center - 2, center + 3):
                mark(row, col)

    for i in range(8, size - 8):
        mark(6, i)
        mark(i, 6)

    for i in range(15):
        if i < 6:
            mark(i, 8)
        elif i < 8:
            mark(i + 1, 8)
        else:
            mark(size - 15 + i, 8)

        if i < 8:
            mark(8, size - i - 1)
        elif i == 8:
            mark(8, 7)
        else:
            mark(8, 14 - i)

    mark(size - 8, 8)
    return function


def _read_format_mask(matrix: list[list[bool]]) -> int:
    size = len(matrix)
    bits = 0

    for i in range(15):
        if i < 6:
            row, col = i, 8
        elif i < 8:
            row, col = i + 1, 8
        else:
            row, col = size - 15 + i, 8

        if matrix[row][col]:
            bits |= 1 << i

    assert bits in _FORMAT_MASK_BY_BITS, f"unknown format bits: {bits:015b}"
    return _FORMAT_MASK_BY_BITS[bits]


def _mask(mask: int, row: int, col: int) -> bool:
    if mask == 0:
        return (row + col) % 2 == 0
    if mask == 1:
        return row % 2 == 0
    if mask == 2:
        return col % 3 == 0
    if mask == 3:
        return (row + col) % 3 == 0
    if mask == 4:
        return (row // 2 + col // 3) % 2 == 0
    if mask == 5:
        return (row * col) % 2 + (row * col) % 3 == 0
    if mask == 6:
        return ((row * col) % 2 + (row * col) % 3) % 2 == 0
    return ((row + col) % 2 + (row * col) % 3) % 2 == 0


def _read_data_bits(matrix: list[list[bool]], mask: int) -> list[int]:
    size = len(matrix)
    function = _mark_function_modules(size)
    bits = []
    row = size - 1
    direction = -1
    col = size - 1

    while col > 0:
        if col == 6:
            col -= 1
        while 0 <= row < size:
            for offset in range(2):
                c = col - offset
                if function[row][c]:
                    continue
                bit = matrix[row][c]
                if _mask(mask, row, c):
                    bit = not bit
                bits.append(1 if bit else 0)
            row += direction
        row -= direction
        direction = -direction
        col -= 2

    return bits


def _decode_rendered_qr(matrix: list[list[bool]]) -> str:
    bits = _read_data_bits(matrix, _read_format_mask(matrix))
    cursor = 0

    def read(length: int) -> int:
        nonlocal cursor
        value = 0
        for bit in bits[cursor : cursor + length]:
            value = (value << 1) | bit
        cursor += length
        return value

    mode = read(4)
    assert mode == 0b0100

    byte_count = read(8)
    payload = bytes(read(8) for _ in range(byte_count))
    return payload.decode("utf-8")


def test_qr_renders_on_wide_terminal() -> None:
    fake_size = namedtuple("Size", "columns lines")(80, 24)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(qrcode.shutil, "get_terminal_size", lambda fallback=(80, 24): fake_size)
    out = io.StringIO()
    try:
        assert qrcode.render_qr("http://localhost:8080/", stream=out)
    finally:
        monkeypatch.undo()
    assert out.getvalue().strip() != ""


def test_qr_uses_forced_terminal_contrast_on_tty() -> None:
    fake_size = namedtuple("Size", "columns lines")(80, 24)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(qrcode.shutil, "get_terminal_size", lambda fallback=(80, 24): fake_size)
    out = _TtyStringIO()
    try:
        assert qrcode.render_qr("http://localhost:8080/", stream=out)
    finally:
        monkeypatch.undo()
    rendered = out.getvalue()
    assert "\x1b[40m" in rendered
    assert "\x1b[107m" in rendered


def test_plain_rendered_qr_output_decodes_to_original_url(monkeypatch: pytest.MonkeyPatch) -> None:
    _wide_terminal(monkeypatch)
    url = "http://192.168.1.205:8080/"
    out = io.StringIO()

    assert qrcode.render_qr(url, stream=out)

    assert _decode_rendered_qr(_parse_plain_rendered_matrix(out.getvalue())) == url


def test_ansi_rendered_qr_output_decodes_to_original_url(monkeypatch: pytest.MonkeyPatch) -> None:
    _wide_terminal(monkeypatch)
    url = "http://localhost:8080/"
    out = _TtyStringIO()

    assert qrcode.render_qr(url, stream=out)

    assert _decode_rendered_qr(_parse_ansi_rendered_matrix(out.getvalue())) == url


def test_qr_payload_limit_is_78_utf8_bytes() -> None:
    multibyte = "\u00e9"

    assert len(("a" * 78).encode("utf-8")) == 78
    assert len((multibyte * 39).encode("utf-8")) == 78

    assert len(qrcode._build_matrix("a" * 78)) == 33
    assert len(qrcode._build_matrix(multibyte * 39)) == 33

    with pytest.raises(ValueError, match="too long"):
        qrcode._build_matrix("a" * 79)
    with pytest.raises(ValueError, match="too long"):
        qrcode._build_matrix(multibyte * 40)


def test_qr_known_format_bits_and_version_selection() -> None:
    assert f"{qrcode._format_bits(0):015b}" == "111011111000100"
    assert len(qrcode._build_matrix("http://localhost:8080/")) == 25
    assert len(qrcode._build_matrix("http://192.168.1.205:8080/")) == 25


def test_reed_solomon_matches_known_version_2_l_codewords() -> None:
    data = qrcode._encode_data(b"http://localhost:8080/", 2)

    assert data == [
        65,
        102,
        135,
        71,
        71,
        3,
        162,
        242,
        246,
        198,
        246,
        54,
        22,
        198,
        134,
        247,
        55,
        67,
        163,
        131,
        3,
        131,
        2,
        240,
        236,
        17,
        236,
        17,
        236,
        17,
        236,
        17,
        236,
        17,
    ]
    assert qrcode._reed_solomon(data, qrcode._ECC_CODEWORDS[2]) == [224, 235, 163, 25, 95, 161, 5, 47, 66, 94]


def test_format_bits_use_dark_module_and_second_copy_positions() -> None:
    size = 25
    matrix = [[None for _ in range(size)] for _ in range(size)]
    function = [[False for _ in range(size)] for _ in range(size)]

    qrcode._draw_function_patterns(matrix, function, 2)
    qrcode._draw_format_bits(matrix, function, 4)
    bits = qrcode._format_bits(4)

    assert matrix[size - 8][8] is True
    assert matrix[0][8] == bool(bits & 1)
    assert matrix[8][size - 1] == bool(bits & 1)
    assert matrix[8][7] == bool((bits >> 8) & 1)
    assert matrix[size - 1][8] == bool(bits & 1)
    assert function[size - 8][8] is True


def test_qr_warns_when_terminal_too_narrow() -> None:
    fake_size = namedtuple("Size", "columns lines")(20, 24)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(qrcode.shutil, "get_terminal_size", lambda fallback=(80, 24): fake_size)
    out = io.StringIO()
    try:
        assert not qrcode.render_qr("http://localhost:8080/", stream=out)
    finally:
        monkeypatch.undo()
    assert "too narrow" in out.getvalue().lower()
