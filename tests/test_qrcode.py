from __future__ import annotations

import io
from collections import namedtuple

import pytest

from http_here import qrcode


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
