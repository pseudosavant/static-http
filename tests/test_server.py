from __future__ import annotations

import contextlib
from http.client import HTTPResponse
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from http_here import server


@contextlib.contextmanager
def _running_server(tmp_path, **kwargs):
    handler = server.make_handler(directory=str(tmp_path), **kwargs)
    host = "127.0.0.1"
    srv = server.ThreadedHTTPServer((host, 0), handler)
    thread = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
    thread.start()
    try:
        yield srv
    finally:
        srv.shutdown()
        thread.join(timeout=1.0)
        srv.server_close()


def _http_url(server_obj: server.ThreadedHTTPServer, path: str) -> str:
    return f"http://127.0.0.1:{server_obj.server_address[1]}{path}"


def test_get_and_head_and_range_requests(tmp_path: Path) -> None:
    content = b"hello world"
    (tmp_path / "file.txt").write_bytes(content)
    kwargs = {
        "extra_headers": {},
        "disable_dir_list": False,
        "quiet": True,
    }
    with _running_server(tmp_path, **kwargs) as srv:
        url = _http_url(srv, "/file.txt")
        with urllib.request.urlopen(url) as resp:
            assert isinstance(resp, HTTPResponse)
            assert resp.status == 200
            assert resp.read() == content

        req = urllib.request.Request(url, headers={"Range": "bytes=0-4"})
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 206
            assert resp.headers["Content-Range"] == "bytes 0-4/11"
            assert resp.read() == content[:5]

        req = urllib.request.Request(url, headers={"Range": "bytes=6-"}, method="GET")
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 206
            assert resp.read() == b"world"

        req = urllib.request.Request(url, headers={"Range": "bytes=-5"})
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 206
            assert resp.read() == b"world"

        req = urllib.request.Request(url, headers={"Range": "bytes=20-30"})
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(req)
        assert exc.value.code == 416


def test_head_returns_headers_without_body(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_bytes(b"abc")
    with _running_server(
        tmp_path,
        extra_headers={},
        disable_dir_list=False,
        quiet=True,
    ) as srv:
        req = urllib.request.Request(_http_url(srv, "/hello.txt"), method="HEAD")
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            assert resp.headers["Content-Length"] == "3"
            assert resp.read() == b""


def test_headers_and_directory_listing_controls(tmp_path: Path) -> None:
    root = tmp_path / "dir"
    root.mkdir()
    (root / "index.txt").write_bytes(b"index")
    (tmp_path / "a b.txt").write_bytes(b"space")
    (tmp_path / ".hidden.txt").write_bytes(b"secret")
    (tmp_path / "rootdir").mkdir()

    with _running_server(
        tmp_path,
        extra_headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store"},
        disable_dir_list=False,
        quiet=True,
    ) as srv:
        list_url = _http_url(srv, "/")
        with urllib.request.urlopen(list_url) as resp:
            assert resp.status == 200
            assert resp.headers["Access-Control-Allow-Origin"] == "*"
            assert resp.headers["Cache-Control"] == "no-store"
            body = resp.read()
            assert b"a b.txt" in body or b"a+b.txt" in body
            assert b".hidden.txt" not in body

        req = urllib.request.Request(_http_url(srv, "/a%20b.txt"))
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            assert resp.read() == b"space"
            assert resp.headers["Access-Control-Allow-Origin"] == "*"
            assert resp.headers["Cache-Control"] == "no-store"

        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(_http_url(srv, "/.hidden.txt"))
        assert exc.value.code in {400, 404}

        invalid_date = urllib.request.Request(_http_url(srv, "/a%20b.txt"), headers={"If-Modified-Since": "not a date"})
        with urllib.request.urlopen(invalid_date) as resp:
            assert resp.status == 200
            assert resp.read() == b"space"

    with _running_server(
        tmp_path,
        extra_headers={},
        disable_dir_list=True,
        quiet=True,
    ) as srv:
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(_http_url(srv, "/"))
        assert exc.value.code == 403


def test_show_hidden_handler_option_exposes_hidden_entries(tmp_path: Path) -> None:
    (tmp_path / ".hidden.txt").write_bytes(b"secret")

    with _running_server(
        tmp_path,
        extra_headers={},
        disable_dir_list=False,
        quiet=True,
        show_hidden=True,
    ) as srv:
        list_url = _http_url(srv, "/")
        with urllib.request.urlopen(list_url) as resp:
            assert resp.status == 200
            body = resp.read()
            assert b".hidden.txt" in body

        with urllib.request.urlopen(_http_url(srv, "/.hidden.txt")) as resp:
            assert resp.status == 200
            assert resp.read() == b"secret"


def test_path_traversal_cannot_escape_root(tmp_path: Path) -> None:
    (tmp_path / "inside.txt").write_bytes(b"inside")
    (tmp_path / "outside.txt").write_bytes(b"fake-outside")
    (tmp_path.parent / "outside.txt").write_bytes(b"outside")

    with _running_server(
        tmp_path,
        extra_headers={},
        disable_dir_list=False,
        quiet=True,
    ) as srv:
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(_http_url(srv, "/../outside.txt"))
        assert exc.value.code in {400, 404}

        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(_http_url(srv, "/%2e%2e/outside.txt"))
        assert exc.value.code == 400

        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(_http_url(srv, "/inside%5c.txt"))
        assert exc.value.code in {400, 404, 200}


def test_directory_redirect_preserves_query_string(tmp_path: Path) -> None:
    (tmp_path / "dir").mkdir()

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
            return None

    opener = urllib.request.build_opener(NoRedirect)
    with _running_server(
        tmp_path,
        extra_headers={},
        disable_dir_list=False,
        quiet=True,
    ) as srv:
        with pytest.raises(urllib.error.HTTPError) as exc:
            opener.open(_http_url(srv, "/dir?download=1"))
        assert exc.value.code == 301
        assert exc.value.headers["Location"] == "/dir/?download=1"

        with urllib.request.urlopen(_http_url(srv, "/dir/?download=1")) as resp:
            assert resp.status == 200
