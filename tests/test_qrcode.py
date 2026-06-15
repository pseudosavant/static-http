from __future__ import annotations

import io
from collections import namedtuple

import pytest

from http_here import qrcode


class _TtyStringIO(io.StringIO):
    def isatty(self) -> bool:
        return True


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
