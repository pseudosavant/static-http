from __future__ import annotations

from http_here.urls import get_preferred_open_url, get_preferred_qr_url, get_startup_urls


def test_startup_urls_include_localhost_when_binding_all_interfaces() -> None:
    urls = get_startup_urls("0.0.0.0", 8080, discovered_lan=["192.168.1.2"])
    assert "http://0.0.0.0:8080/" in urls
    assert "http://localhost:8080/" in urls


def test_preferred_open_url_uses_localhost_for_all_interfaces() -> None:
    assert get_preferred_open_url("0.0.0.0", 8080, discovered_lan=["192.168.1.2"]) == "http://localhost:8080/"


def test_preferred_qr_url_prefers_lan_for_all_interfaces() -> None:
    assert get_preferred_qr_url("0.0.0.0", 8080, discovered_lan=["192.168.1.2"]) == "http://192.168.1.2:8080/"

