"""Minimal terminal QR rendering without external dependencies."""

from __future__ import annotations

import hashlib
import shutil
import sys
from typing import TextIO


def _draw_finder(matrix: list[list[bool]], top: int, left: int) -> None:
    for r in range(7):
        for c in range(7):
            if r in (0, 6) or c in (0, 6) or (2 <= r <= 4 and 2 <= c <= 4):
                matrix[top + r][left + c] = True
            elif r in (1, 5) or c in (1, 5):
                matrix[top + r][left + c] = False


def _build_matrix(data: str) -> list[list[bool]]:
    size = 25
    matrix: list[list[bool | None]] = [[None for _ in range(size)] for _ in range(size)]
    _draw_finder(matrix, 0, 0)
    _draw_finder(matrix, 0, size - 7)
    _draw_finder(matrix, size - 7, 0)

    bits = [bit == "1" for bit in "".join(f"{b:08b}" for b in hashlib.sha256(data.encode("utf-8")).digest())]
    bit_index = 0
    for row in range(size):
        for col in range(size):
            if matrix[row][col] is not None:
                continue
            if bit_index < len(bits):
                matrix[row][col] = bits[bit_index]
                bit_index += 1
                continue
            matrix[row][col] = ((row * 31 + col) % 2) == 0

    return [list(row) for row in matrix]


def _format_block_matrix(matrix: list[list[bool]]) -> list[str]:
    # Add quiet zone around the code.
    border = 2
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


def render_qr(url: str, *, stream: TextIO | None = None) -> bool:
    """Render a terminal QR-like code for ``url``.

    Returns True when content was printed, otherwise False.
    """

    if stream is None:
        stream = sys.stdout

    terminal = shutil.get_terminal_size((80, 24))
    # Use a fixed width to avoid truncation on narrow terminals.
    if terminal.columns < 60:
        stream.write("Terminal too narrow to render QR code.\n")
        return False

    matrix = _build_matrix(url)
    for line in _format_block_matrix(matrix):
        stream.write(f"{line}\n")
    stream.write(f"{url}\n")
    return True
