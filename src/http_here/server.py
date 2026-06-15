"""HTTP server with custom range handling and constrained path mapping."""

from __future__ import annotations

import io
import os
import posixpath
import stat
import urllib.parse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from typing import Mapping

from .ranges import RangeParseError, UnsatisfiableRangeError, content_range, parse_range_header, unsatisfiable_content_range


class RangeAwareHTTPRequestHandler(SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler variant with single-range support."""

    def __init__(
        self,
        *args,
        directory: str,
        extra_headers: Mapping[str, str],
        disable_dir_list: bool,
        quiet: bool,
        **kwargs,
    ) -> None:
        self._extra_headers = dict(extra_headers)
        self._disable_dir_list = disable_dir_list
        self._quiet = quiet
        super().__init__(*args, directory=directory, **kwargs)

    def _add_custom_headers(self) -> None:
        for name, value in self._extra_headers.items():
            self.send_header(name, value)

    def log_message(self, format: str, *args) -> None:
        if self._quiet:
            return
        super().log_message(format, *args)

    def translate_path(self, path: str) -> str | None:
        # Safe path mapping inspired by SimpleHTTPRequestHandler, with strict traversal defense.
        path = path.split("?", 1)[0]
        path = path.split("#", 1)[0]
        path = urllib.parse.unquote(path)
        path = path.replace("\\", "/")
        if "\x00" in path:
            return None

        path = posixpath.normpath(path)
        if path == "/":
            parts: list[str] = []
        else:
            parts = []
            for segment in path.split("/"):
                if segment in ("", "."):
                    continue
                if segment == "..":
                    continue
                if ":" in segment:
                    return None
                parts.append(segment)

        candidate = self.directory
        for part in parts:
            candidate = os.path.join(candidate, part)

        candidate = os.path.normpath(candidate)
        root = os.path.realpath(self.directory)
        real_candidate = os.path.realpath(candidate)
        if os.path.commonpath([real_candidate, root]) != root:
            return None

        return candidate

    def _handle_unsatisfiable_range(self, size: int) -> None:
        self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
        self.send_header("Content-Range", unsatisfiable_content_range(size))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", "0")
        self._add_custom_headers()
        self.end_headers()

    def _write_not_modified(self, path: str, mtime: datetime) -> None:
        self.send_response(HTTPStatus.NOT_MODIFIED)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Last-Modified", self.date_time_string(mtime.timestamp()))
        self.send_header("Content-Length", "0")
        self._add_custom_headers()
        self.end_headers()

    def send_head(self) -> io.BufferedIOBase | None:
        path = self.translate_path(self.path)
        if path is None:
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid request path")
            return None

        f = None

        if os.path.isdir(path):
            if not self.path.endswith("/"):
                self.send_response(HTTPStatus.MOVED_PERMANENTLY)
                self.send_header("Location", self.path + "/")
                self._add_custom_headers()
                self.end_headers()
                return None

            for index_name in ("index.html", "index.htm"):
                index_path = os.path.join(path, index_name)
                if os.path.exists(index_path):
                    path = index_path
                    break
            else:
                if self._disable_dir_list:
                    self.send_error(HTTPStatus.FORBIDDEN, "Directory listing is disabled.")
                    return None
                return self.list_directory(path)

        ctype = self.guess_type(path)
        try:
            f = open(path, "rb")
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return None

        try:
            stats = os.fstat(f.fileno())
            if not stat.S_ISREG(stats.st_mode):
                f.close()
                self.send_error(HTTPStatus.NOT_FOUND, "File not found")
                return None

            file_size = stats.st_size
            mtime = datetime.fromtimestamp(stats.st_mtime, tz=timezone.utc)

            if_modified_since = self.headers.get("If-Modified-Since")
            if if_modified_since:
                parsed = parsedate_to_datetime(if_modified_since)
                if parsed is not None:
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    if mtime <= parsed:
                        self._write_not_modified(path, mtime)
                        f.close()
                        return None

            start = end = None
            range_header = self.headers.get("Range")
            if range_header:
                try:
                    start, end = parse_range_header(range_header, file_size)
                except UnsatisfiableRangeError as exc:
                    self._handle_unsatisfiable_range(file_size)
                    f.close()
                    return None
                except RangeParseError as exc:
                    self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
                    f.close()
                    return None

            if start is None:
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Length", str(file_size))
            else:
                self.send_response(HTTPStatus.PARTIAL_CONTENT)
                self.send_header("Content-Range", content_range(start, end, file_size))
                self.send_header("Content-Length", str(end - start + 1))
                f.seek(start)
                f = _RangeFile(f, end - start + 1)

            self.send_header("Content-Type", ctype)
            self.send_header("Last-Modified", self.date_time_string(stats.st_mtime))
            self.send_header("Accept-Ranges", "bytes")
            self._add_custom_headers()
            self.end_headers()
            return f
        except Exception:
            f.close()
            raise


class _RangeFile:
    def __init__(self, wrapped: io.BufferedReader, remaining: int) -> None:
        self._wrapped = wrapped
        self._remaining = remaining

    def read(self, size: int = -1) -> bytes:
        if self._remaining <= 0:
            return b""
        if size < 0 or size > self._remaining:
            size = self._remaining
        data = self._wrapped.read(size)
        self._remaining -= len(data)
        return data

    def close(self) -> None:
        self._wrapped.close()


class ThreadedHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def make_handler(*, directory: str, extra_headers: Mapping[str, str], disable_dir_list: bool, quiet: bool):
    def _factory(*args, **kwargs):
        return RangeAwareHTTPRequestHandler(
            *args,
            directory=directory,
            extra_headers=extra_headers,
            disable_dir_list=disable_dir_list,
            quiet=quiet,
            **kwargs,
        )

    return _factory
