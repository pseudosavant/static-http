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
