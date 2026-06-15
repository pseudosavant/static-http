"""Utilities for computing and formatting URLs for startup output and helpers."""

from __future__ import annotations

import socket
from typing import Iterable, List


def is_all_interfaces_bind(host: str) -> bool:
    return host in {"0.0.0.0", "::", "[::]", "::0", "0:0:0:0:0:0:0:0"}


def format_url(host: str, port: int) -> str:
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"http://{host}:{port}/"


def discover_lan_urls() -> List[str]:
    """Best-effort discovery of likely LAN IPv4 addresses."""

    addresses = []
    seen = set()

    def _add(addr: str) -> None:
        if not addr:
            return
        if addr.startswith("127.") or addr == "0.0.0.0" or addr.startswith("169.254."):
            return
        if addr in seen:
            return
        addresses.append(addr)
        seen.add(addr)

    try:
        _addrinfo_name = socket.gethostname()
        for info in socket.getaddrinfo(_addrinfo_name, None, family=socket.AF_INET, type=socket.SOCK_STREAM):
            _add(info[4][0])
    except OSError:
        pass

    try:
        host_ips = socket.gethostbyname_ex(socket.gethostname())[2]
        for addr in host_ips:
            _add(addr)
    except OSError:
        pass

    # Common trick: let UDP stack pick the local outbound interface.
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("1.1.1.1", 80))
            _add(sock.getsockname()[0])
        finally:
            sock.close()
    except OSError:
        pass

    return list(addresses)


def get_startup_urls(bind_host: str, port: int, discovered_lan: Iterable[str] | None = None) -> list[str]:
    if discovered_lan is None:
        discovered_lan = discover_lan_urls()

    urls: list[str] = [format_url(bind_host, port)]
    if is_all_interfaces_bind(bind_host):
        urls.append(format_url("localhost", port))
        for addr in discovered_lan:
            if addr == "127.0.0.1":
                continue
            urls.append(format_url(addr, port))

    deduped = []
    seen = set()
    for url in urls:
        if url in seen:
            continue
        deduped.append(url)
        seen.add(url)
    return deduped


def get_preferred_open_url(bind_host: str, port: int, discovered_lan: Iterable[str] | None = None) -> str:
    if is_all_interfaces_bind(bind_host):
        return format_url("localhost", port)
    return format_url(bind_host, port)


def get_preferred_qr_url(bind_host: str, port: int, discovered_lan: Iterable[str] | None = None) -> str:
    if is_all_interfaces_bind(bind_host):
        lan = list(discovered_lan or discover_lan_urls())
        if lan:
            return format_url(lan[0], port)
    return get_preferred_open_url(bind_host, port, discovered_lan=discovered_lan)
