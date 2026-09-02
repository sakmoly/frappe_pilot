from __future__ import annotations

from pilot.core.site.login import site_http_port
from pilot.config import BenchConfig


def test_site_http_port_uses_site_config_nginx_port() -> None:
    config = BenchConfig.default("main")
    site_config = {"nginx_port": 88}

    assert site_http_port(site_config, config) == 88


def test_site_http_port_reads_port_from_host_name() -> None:
    config = BenchConfig.default("main")
    site_config = {"host_name": "http://example.com:88"}

    assert site_http_port(site_config, config) == 88


def test_site_http_port_falls_back_to_bench_default() -> None:
    config = BenchConfig.default("main")

    assert site_http_port({}, config) == config.nginx.http_port
