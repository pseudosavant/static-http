"""Minimal terminal QR rendering without external dependencies."""

from __future__ import annotations

import shutil
import sys
from typing import TextIO


_ECC_CODEWORDS = {
    1: 7,
    2: 10,
    3: 15,
    4: 20,
}
_DATA_CODEWORDS = {
    1: 19,
    2: 34,
    3: 55,
    4: 80,
}
_ANSI_BLACK = "\x1b[40m"
_ANSI_WHITE = "\x1b[107m"
_ANSI_RESET = "\x1b[0m"


def _gf_mul(x: int, y: int) -> int:
    result = 0
    while y:
        if y & 1:
            result ^= x
        y >>= 1
        x <<= 1
        if x & 0x100:
            x ^= 0x11D
    return result


def _gf_pow(x: int, power: int) -> int:
    result = 1
    for _ in range(power):
        result = _gf_mul(result, x)
    return result


def _generator_poly(degree: int) -> list[int]:
    result = [1]
    for i in range(degree):
        result = _poly_mul(result, [1, _gf_pow(2, i)])
    return result


def _poly_mul(left: list[int], right: list[int]) -> list[int]:
    result = [0] * (len(left) + len(right) - 1)
    for i, left_value in enumerate(left):
        for j, right_value in enumerate(right):
            result[i + j] ^= _gf_mul(left_value, right_value)
    return result


def _reed_solomon(data: list[int], degree: int) -> list[int]:
    generator = _generator_poly(degree)
    result = data + [0] * degree
    for i, value in enumerate(data):
        if value == 0:
            continue
        for j, coefficient in enumerate(generator):
            result[i + j] ^= _gf_mul(coefficient, value)
    return result[-degree:]


def _append_bits(bits: list[int], value: int, length: int) -> None:
    for i in range(length - 1, -1, -1):
        bits.append((value >> i) & 1)


def _choose_version(data: bytes) -> int:
    needed_bits = 4 + 8 + len(data) * 8
    for version, data_codewords in _DATA_CODEWORDS.items():
        if needed_bits <= data_codewords * 8:
            return version
    raise ValueError("URL is too long for the built-in QR renderer")


def _encode_data(data: bytes, version: int) -> list[int]:
    bits: list[int] = []
    _append_bits(bits, 0b0100, 4)  # Byte mode.
    _append_bits(bits, len(data), 8)
    for byte in data:
        _append_bits(bits, byte, 8)

    capacity = _DATA_CODEWORDS[version] * 8
    _append_bits(bits, 0, min(4, capacity - len(bits)))
    while len(bits) % 8:
        bits.append(0)

    pad = [0xEC, 0x11]
    pad_index = 0
    while len(bits) < capacity:
        _append_bits(bits, pad[pad_index % 2], 8)
        pad_index += 1

    return [int("".join(str(bit) for bit in bits[i : i + 8]), 2) for i in range(0, len(bits), 8)]


def _set_function(matrix: list[list[bool | None]], function: list[list[bool]], row: int, col: int, dark: bool) -> None:
    matrix[row][col] = dark
    function[row][col] = True


def _draw_finder(matrix: list[list[bool | None]], function: list[list[bool]], top: int, left: int) -> None:
    size = len(matrix)
    for r in range(-1, 8):
        for c in range(-1, 8):
            row = top + r
            col = left + c
            if not (0 <= row < size and 0 <= col < size):
                continue
            dark = 0 <= r <= 6 and 0 <= c <= 6 and (r in (0, 6) or c in (0, 6) or (2 <= r <= 4 and 2 <= c <= 4))
            _set_function(matrix, function, row, col, dark)


def _draw_alignment(matrix: list[list[bool | None]], function: list[list[bool]], center: int) -> None:
    for r in range(-2, 3):
        for c in range(-2, 3):
            dark = max(abs(r), abs(c)) != 1
            _set_function(matrix, function, center + r, center + c, dark)


def _draw_function_patterns(matrix: list[list[bool | None]], function: list[list[bool]], version: int) -> None:
    size = len(matrix)
    _draw_finder(matrix, function, 0, 0)
    _draw_finder(matrix, function, 0, size - 7)
    _draw_finder(matrix, function, size - 7, 0)
    if version > 1:
        _draw_alignment(matrix, function, size - 7)

    for i in range(8, size - 8):
        _set_function(matrix, function, 6, i, i % 2 == 0)
        _set_function(matrix, function, i, 6, i % 2 == 0)

    _set_function(matrix, function, size - 8, 8, True)
    _draw_format_bits(matrix, function, 0)


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


def _draw_codewords(matrix: list[list[bool | None]], function: list[list[bool]], codewords: list[int], mask: int) -> None:
    bits = [(codeword >> i) & 1 for codeword in codewords for i in range(7, -1, -1)]
    bit_index = 0
    size = len(matrix)
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
                bit = bit_index < len(bits) and bits[bit_index] == 1
                bit_index += 1
                matrix[row][c] = bit ^ _mask(mask, row, c)
            row += direction
        row -= direction
        direction = -direction
        col -= 2


def _format_bits(mask: int) -> int:
    data = (0b01 << 3) | mask  # Error correction level L.
    value = data << 10
    generator = 0b10100110111
    for i in range(14, 9, -1):
        if (value >> i) & 1:
            value ^= generator << (i - 10)
    return (((data << 10) | value) ^ 0b101010000010010) & 0x7FFF


def _draw_format_bits(matrix: list[list[bool | None]], function: list[list[bool]], mask: int) -> None:
    bits = _format_bits(mask)
    size = len(matrix)
    positions_a = [
        (8, 0),
        (8, 1),
        (8, 2),
        (8, 3),
        (8, 4),
        (8, 5),
        (8, 7),
        (8, 8),
        (7, 8),
        (5, 8),
        (4, 8),
        (3, 8),
        (2, 8),
        (1, 8),
        (0, 8),
    ]
    positions_b = [
        (size - 1, 8),
        (size - 2, 8),
        (size - 3, 8),
        (size - 4, 8),
        (size - 5, 8),
        (size - 6, 8),
        (size - 7, 8),
        (8, size - 8),
        (8, size - 7),
        (8, size - 6),
        (8, size - 5),
        (8, size - 4),
        (8, size - 3),
        (8, size - 2),
        (8, size - 1),
    ]
    for i, (row, col) in enumerate(positions_a):
        _set_function(matrix, function, row, col, ((bits >> i) & 1) == 1)
    for i, (row, col) in enumerate(positions_b):
        _set_function(matrix, function, row, col, ((bits >> i) & 1) == 1)


def _penalty(matrix: list[list[bool | None]]) -> int:
    size = len(matrix)
    penalty = 0
    for row in range(size):
        run_color = matrix[row][0]
        run_length = 1
        for col in range(1, size):
            if matrix[row][col] == run_color:
                run_length += 1
            else:
                if run_length >= 5:
                    penalty += run_length - 2
                run_color = matrix[row][col]
                run_length = 1
        if run_length >= 5:
            penalty += run_length - 2

    for col in range(size):
        run_color = matrix[0][col]
        run_length = 1
        for row in range(1, size):
            if matrix[row][col] == run_color:
                run_length += 1
            else:
                if run_length >= 5:
                    penalty += run_length - 2
                run_color = matrix[row][col]
                run_length = 1
        if run_length >= 5:
            penalty += run_length - 2

    for row in range(size - 1):
        for col in range(size - 1):
            color = matrix[row][col]
            if color == matrix[row + 1][col] == matrix[row][col + 1] == matrix[row + 1][col + 1]:
                penalty += 3

    dark = sum(1 for row in matrix for cell in row if cell)
    total = size * size
    penalty += abs(dark * 20 - total * 10) // total * 10
    return penalty


def _build_matrix(data: str) -> list[list[bool]]:
    payload = data.encode("utf-8")
    version = _choose_version(payload)
    size = version * 4 + 17
    data_codewords = _encode_data(payload, version)
    codewords = data_codewords + _reed_solomon(data_codewords, _ECC_CODEWORDS[version])

    best_matrix: list[list[bool | None]] | None = None
    best_penalty: int | None = None
    for mask in range(8):
        matrix: list[list[bool | None]] = [[None for _ in range(size)] for _ in range(size)]
        function = [[False for _ in range(size)] for _ in range(size)]
        _draw_function_patterns(matrix, function, version)
        _draw_codewords(matrix, function, codewords, mask)
        _draw_format_bits(matrix, function, mask)
        penalty = _penalty(matrix)
        if best_penalty is None or penalty < best_penalty:
            best_matrix = matrix
            best_penalty = penalty

    if best_matrix is None:
        raise AssertionError("QR matrix was not generated")
    return [[bool(cell) for cell in row] for row in best_matrix]


def _format_plain_block_matrix(matrix: list[list[bool]]) -> list[str]:
    border = 4
    width = len(matrix)
    lines: list[str] = []
    for _ in range(border):
        lines.append(" " * ((width + border * 2) * 2))

    for row in matrix:
        line = "  " * border
        for cell in row:
            line += "██" if cell else "  "
        line += "  " * border
        lines.append(line)

    for _ in range(border):
        lines.append(" " * ((width + border * 2) * 2))
    return lines


def _format_ansi_block_matrix(matrix: list[list[bool]]) -> list[str]:
    border = 4
    light_row = _ANSI_WHITE + (" " * ((len(matrix) + border * 2) * 2)) + _ANSI_RESET
    lines: list[str] = [light_row for _ in range(border)]

    for row in matrix:
        line = [_ANSI_WHITE + ("  " * border)]
        last_color = _ANSI_WHITE
        for cell in row:
            color = _ANSI_BLACK if cell else _ANSI_WHITE
            if color != last_color:
                line.append(color)
                last_color = color
            line.append("  ")
        if last_color != _ANSI_WHITE:
            line.append(_ANSI_WHITE)
        line.append("  " * border)
        line.append(_ANSI_RESET)
        lines.append("".join(line))

    lines.extend(light_row for _ in range(border))
    return lines


def _supports_ansi(stream: TextIO) -> bool:
    isatty = getattr(stream, "isatty", None)
    return bool(isatty and isatty())


def render_qr(url: str, *, stream: TextIO | None = None) -> bool:
    """Render a terminal QR code for ``url``."""

    if stream is None:
        stream = sys.stdout

    try:
        matrix = _build_matrix(url)
    except ValueError as exc:
        stream.write(f"{exc}\n")
        return False

    terminal = shutil.get_terminal_size((80, 24))
    required_columns = (len(matrix) + 8) * 2
    if terminal.columns < required_columns:
        stream.write(f"Terminal too narrow to render QR code. Need at least {required_columns} columns.\n")
        return False

    formatter = _format_ansi_block_matrix if _supports_ansi(stream) else _format_plain_block_matrix
    for line in formatter(matrix):
        stream.write(f"{line}\n")
    stream.write(f"{url}\n")
    return True
