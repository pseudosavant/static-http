"""HTTP server with custom range handling and constrained path mapping."""

from __future__ import annotations

import html
import io
import os
import stat
import sys
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
        show_hidden: bool,
        **kwargs,
    ) -> None:
        self._extra_headers = dict(extra_headers)
        self._disable_dir_list = disable_dir_list
        self._quiet = quiet
        self._show_hidden = show_hidden
        super().__init__(*args, directory=directory, **kwargs)

    def _add_custom_headers(self) -> None:
        for name, value in self._extra_headers.items():
            self.send_header(name, value)

    def log_message(self, format: str, *args) -> None:
        if self._quiet:
            return
        super().log_message(format, *args)

    def log_error(self, format: str, *args) -> None:
        if self._quiet:
            return
        super().log_error(format, *args)

    def _is_hidden(self, segment: str) -> bool:
        if self._show_hidden:
            return False
        return segment.startswith(".")

    def _has_hidden_attribute(self, path: str) -> bool:
        if self._show_hidden:
            return False
        hidden_flag = getattr(stat, "FILE_ATTRIBUTE_HIDDEN", 0)
        if not hidden_flag:
            return False
        try:
            return bool(os.stat(path).st_file_attributes & hidden_flag)
        except (AttributeError, OSError):
            return False

    def _is_hidden_entry(self, name: str, path: str) -> bool:
        return self._is_hidden(name) or self._has_hidden_attribute(path)

    def translate_path(self, path: str) -> str | None:
        # Safe path mapping inspired by SimpleHTTPRequestHandler, with strict traversal defense.
        path = path.split("?", 1)[0]
        path = path.split("#", 1)[0]
        path = urllib.parse.unquote(path)
        path = path.replace("\\", "/")
        if "\x00" in path:
            return None

        parts = []
        for segment in path.split("/"):
            if segment in ("", "."):
                continue
            if segment == "..":
                return None
            if self._is_hidden(segment):
                return None
            if ":" in segment:
                return None
            parts.append(segment)

        candidate = self.directory
        for part in parts:
            candidate = os.path.join(candidate, part)
            if self._has_hidden_attribute(candidate):
                return None

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
            parts = urllib.parse.urlsplit(self.path)
            if not parts.path.endswith("/"):
                location = urllib.parse.urlunsplit(("", "", parts.path + "/", parts.query, parts.fragment))
                self.send_response(HTTPStatus.MOVED_PERMANENTLY)
                self.send_header("Location", location)
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
                try:
                    parsed = parsedate_to_datetime(if_modified_since)
                except (IndexError, OverflowError, TypeError, ValueError):
                    parsed = None
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

    def list_directory(self, path: str) -> io.BytesIO | None:
        try:
            listdir = os.listdir(path)
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND, "No permission to list directory")
            return None

        listdir = [entry for entry in listdir if not self._is_hidden_entry(entry, os.path.join(path, entry))]
        listdir.sort(key=lambda a: a.lower())
        r = []

        try:
            displaypath = urllib.parse.unquote(self.path, errors="surrogatepass")
        except UnicodeDecodeError:
            displaypath = urllib.parse.unquote(self.path)
        displaypath = html.escape(displaypath)

        enc = "UTF-8"
        title = f"Directory listing for {displaypath}"
        r.append("<!DOCTYPE html>\n")
        r.append("<html>\n<head>\n")
        r.append(f'<meta charset="{enc}">\n')
        r.append(f"<title>{title}</title>\n")
        r.append("</head>\n<body>\n")
        r.append(f"<h1>{title}</h1>\n<hr>\n<ul>\n")

        for name in listdir:
            full_name = os.path.join(path, name)
            displayname = linkname = name
            if os.path.isdir(full_name):
                displayname = name + "/"
                linkname = name + "/"
            if os.path.islink(full_name):
                displayname = name + "@"

            r.append(
                f'<li><a href="{urllib.parse.quote(linkname, errors="surrogatepass")}">'
                f"{html.escape(displayname)}</a></li>\n"
            )

        r.append("</ul>\n<hr>\n</body>\n</html>\n")
        encoded = "".join(r).encode(enc, "surrogateescape")

        f = io.BytesIO()
        f.write(encoded)
        f.seek(0)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"text/html; charset={enc}")
        self.send_header("Content-Length", str(len(encoded)))
        self._add_custom_headers()
        self.end_headers()
        return f


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

    def handle_error(self, request, client_address) -> None:  # type: ignore[override]
        exc = sys.exc_info()[1]
        if (
            not bool(getattr(self, "verbose", False))
            and isinstance(exc, (BrokenPipeError, ConnectionAbortedError, ConnectionResetError))
        ):
            return
        super().handle_error(request, client_address)


def make_handler(*, directory: str, extra_headers: Mapping[str, str], disable_dir_list: bool, quiet: bool, show_hidden: bool = False):
    def _factory(*args, **kwargs):
        return RangeAwareHTTPRequestHandler(
            *args,
            directory=directory,
            extra_headers=extra_headers,
            disable_dir_list=disable_dir_list,
            quiet=quiet,
            show_hidden=show_hidden,
            **kwargs,
        )

    return _factory
