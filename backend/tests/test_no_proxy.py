"""Tests for proxy-environment normalization."""

from backend import sanitize_no_proxy_environment


def test_sanitize_no_proxy_removes_only_ipv6_loopback_entries():
    environment = {
        "NO_PROXY": "localhost,example.com:8080,::1,[::1],[::1]:8120,10.0.0.1:3128",
        "no_proxy": "api.internal:9000,127.0.0.1",
    }

    sanitize_no_proxy_environment(environment)

    assert environment["NO_PROXY"] == (
        "localhost,example.com:8080,10.0.0.1:3128"
    )
    assert environment["no_proxy"] == "api.internal:9000,127.0.0.1"
