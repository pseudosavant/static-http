"""CLI entrypoint and lifecycle management for static-http."""

from __future__ import annotations

import argparse
import os
import sys
import threading
import webbrowser
from pathlib import Path

from . import __version__
from .keyboard import start_quit_watcher
from . import qrcode as qrcode_module
from . import urls
from .server import ThreadedHTTPServer, make_handler


def _parse_port(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Port must be an integer") from exc
    if value < 0 or value > 65535:
        raise argparse.ArgumentTypeError("Port must be between 0 and 65535")
    return value


def _parse_directory(raw: str) -> str:
    candidate = Path(raw).expanduser()
    if not candidate.exists():
        raise argparse.ArgumentTypeError(f"Directory does not exist: {candidate}")
    if not candidate.is_dir():
        raise argparse.ArgumentTypeError(f"Not a directory: {candidate}")
    return str(candidate.resolve())


def _parse_header(raw: str) -> tuple[str, str]:
    if ":" not in raw:
        raise argparse.ArgumentTypeError("Header must use Name: Value format")
    name, value = raw.split(":", 1)
    name = name.strip()
    value = value.strip()
    if not name:
        raise argparse.ArgumentTypeError("Header name cannot be empty")
    if ":" in name:
        raise argparse.ArgumentTypeError("Header name must not contain ':'")
    if "\r" in name or "\n" in name or "\r" in value or "\n" in value:
        raise argparse.ArgumentTypeError("Header values may not contain CR or LF")
    return name, value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="static-http", description="Serve static files with byte-range support.")
    parser.add_argument(
        "-p",
        "--port",
        type=_parse_port,
        default=8080,
        help="Port to listen on (0 for an OS-assigned ephemeral port).",
    )
    parser.add_argument(
        "-d",
        "--directory",
        type=_parse_directory,
        default=str(Path.cwd()),
        help="Directory to serve.",
    )

    bind_group = parser.add_mutually_exclusive_group()
    bind_group.add_argument(
        "-b",
        "--bind",
        default="0.0.0.0",
        help="Address to bind.",
    )
    bind_group.add_argument(
        "--localhost-only",
        action="store_true",
        help="Bind only to 127.0.0.1.",
    )

    parser.add_argument(
        "--cors",
        action="store_true",
        help="Add Access-Control-Allow-Origin: *.",
    )
    parser.add_argument(
        "--header",
        action="append",
        type=_parse_header,
        default=[],
        metavar="\"Name: Value\"",
        help='Add a response header. Repeatable.',
    )
    parser.add_argument(
        "--no-dir-list",
        action="store_true",
        help="Disable directory listing when no index file exists.",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open the server URL in a browser after startup.",
    )
    parser.add_argument(
        "--qr",
        action="store_true",
        help="Render a terminal QR code for the chosen URL.",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Send Cache-Control: no-store.",
    )

    quiet_verbose_group = parser.add_mutually_exclusive_group()
    quiet_verbose_group.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-request logs.",
    )
    quiet_verbose_group.add_argument(
        "--verbose",
        action="store_true",
        help="Print extra startup and binding information.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=__version__,
    )
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.localhost_only:
        args.bind = "127.0.0.1"
    return args


def build_response_headers(*, cors: bool, no_cache: bool, headers: list[tuple[str, str]]) -> dict[str, str]:
    merged: dict[str, str] = {}
    if cors:
        merged["Access-Control-Allow-Origin"] = "*"
    if no_cache:
        merged["Cache-Control"] = "no-store"

    for name, value in headers:
        merged[name] = value
    return merged


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
    except SystemExit as exc:
        if exc.code is None:
            return 0
        return int(exc.code) if isinstance(exc.code, int) else 2

    root = str(Path(args.directory).resolve())
    bind_host = args.bind
    bind_port = args.port

    response_headers = build_response_headers(cors=args.cors, no_cache=args.no_cache, headers=args.header)

    handler = make_handler(
        directory=root,
        extra_headers=response_headers,
        disable_dir_list=args.no_dir_list,
        quiet=args.quiet,
    )

    try:
        server = ThreadedHTTPServer((bind_host, bind_port), handler)
    except OSError as exc:
        print(f"Could not bind {bind_host}:{bind_port}: {exc}", file=sys.stderr)
        return 1

    actual_bind = server.server_address[0]
    actual_port = server.server_address[1]
    discovered_lan = urls.discover_lan_urls() if urls.is_all_interfaces_bind(actual_bind) else []
    startup_urls = urls.get_startup_urls(actual_bind, actual_port, discovered_lan=discovered_lan)

    print(f"Serving {root} at:")
    for item in startup_urls:
        if item:
            print(f"  {item}")
    print("Press Q to quit.")

    if args.verbose:
        print(f"Root directory: {root}")
        print(f"Bound address: {actual_bind}")
        print(f"Port: {actual_port}")
        if discovered_lan:
            print("Discovered LAN URLs:")
            for item in discovered_lan:
                print(f"  http://{item}:{actual_port}/")

    shutdown_event = threading.Event()

    def _shutdown() -> None:
        if shutdown_event.is_set():
            return
        shutdown_event.set()
        print("Shutting down.")
        threading.Thread(target=server.shutdown, name="static-http-shutdown", daemon=True).start()

    server_thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.5}, name="static-http-server", daemon=True)
    server_thread.start()

    open_url = urls.get_preferred_open_url(actual_bind, actual_port, discovered_lan=discovered_lan)
    if args.open:
        try:
            if not webbrowser.open(open_url):
                print(f"Warning: could not open browser for {open_url}", file=sys.stderr)
        except Exception as exc:
            print(f"Warning: could not open browser: {exc}", file=sys.stderr)

    if args.qr:
        qr_url = urls.get_preferred_qr_url(actual_bind, actual_port, discovered_lan=discovered_lan)
        if not qrcode_module.render_qr(qr_url):
            print(f"Warning: QR code could not be rendered for {qr_url}", file=sys.stderr)

    stop_event, needs_enter = start_quit_watcher(_shutdown)
    if needs_enter:
        print("Press q then Enter to quit.")

    try:
        while not shutdown_event.wait(0.25):
            pass
    except KeyboardInterrupt:
        _shutdown()
        while not shutdown_event.wait(0.25):
            pass

    stop_event.set()
    server_thread.join(timeout=2.0)
    server.server_close()
    return 0
