from __future__ import annotations

from pathlib import Path

import pytest

from http_here.cli import build_response_headers, parse_args


def test_default_cli_values(tmp_path) -> None:
    args = parse_args([])
    assert args.port == 8080
    assert args.bind == "0.0.0.0"
    assert args.directory == str(Path.cwd())


def test_port_zero_is_accepted() -> None:
    args = parse_args(["--port", "0"])
    assert args.port == 0


def test_invalid_port_rejected() -> None:
    with pytest.raises(SystemExit):
        parse_args(["--port", "-1"])
    with pytest.raises(SystemExit):
        parse_args(["--port", "70000"])


def test_no_positional_arguments_are_rejected() -> None:
    with pytest.raises(SystemExit):
        parse_args(["9000"])


def test_localhost_only_and_bind_conflict() -> None:
    with pytest.raises(SystemExit):
        parse_args(["--localhost-only", "--bind", "127.0.0.1"])


def test_localhost_only_maps_to_loopback() -> None:
    args = parse_args(["--localhost-only"])
    assert args.bind == "127.0.0.1"


def test_invalid_directory_rejected(tmp_path) -> None:
    with pytest.raises(SystemExit):
        parse_args(["--directory", str(tmp_path / "missing")])
    missing = tmp_path / "not-a-directory"
    missing.write_text("hello")
    with pytest.raises(SystemExit):
        parse_args(["--directory", str(missing)])


def test_header_precedence_and_cors() -> None:
    headers = build_response_headers(
        cors=True,
        no_cache=True,
        headers=[("Cache-Control", "max-age=60"), ("X-Test", "1"), ("Cache-Control", "private")],
    )
    assert headers["Access-Control-Allow-Origin"] == "*"
    assert headers["Cache-Control"] == "private"
    assert headers["X-Test"] == "1"
