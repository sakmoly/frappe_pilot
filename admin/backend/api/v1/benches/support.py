from __future__ import annotations

import re
from pathlib import Path

from flask import current_app

from admin.backend.api.responses import error_response
from admin.backend.providers.bench import BenchProvider
from pilot.config import BenchConfig
from pilot.config.admin import default_allow_bench_management

BENCH_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
ADMIN_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$"
)


def guard_bench_management():
    """Gate bench-management routes behind admin.allow_bench_management."""
    bench_root = Path(current_app.config["BENCH_ROOT"])
    try:
        config = BenchConfig.read_raw(bench_root)
    except Exception:
        return error_response(
            "bench_management_forbidden",
            "Bench management is disabled on this server.",
            403,
        )

    if not config.get("admin", {}).get("allow_bench_management", default_allow_bench_management()):
        return error_response(
            "bench_management_forbidden",
            "Bench management is disabled on this server.",
            403,
        )
    return None


def bench_resource(bench_dir: Path) -> dict:
    toml_path = bench_dir / "bench.toml"
    config = BenchConfig.read_raw(toml_path)
    bench_name = config.get("bench", {}).get("name")
    if not isinstance(bench_name, str) or not bench_name.strip():
        bench_name = bench_dir.name
    admin_config = config.get("admin", {})
    production_config = config.get("production", {})
    port = admin_config.get("port")
    if not isinstance(port, int) or isinstance(port, bool):
        raise ValueError("Bench admin port is unavailable")

    process_manager = _process_manager_name(production_config.get("process_manager", ""))
    enabled = production_config.get("enabled")
    production = enabled if isinstance(enabled, bool) else process_manager != ""
    domain = admin_config.get("domain", "")
    if not isinstance(domain, str):
        domain = ""

    bench = BenchProvider(bench_dir)
    tls = admin_config.get("tls") is True
    scheme = "https" if tls and bench.has_admin_cert else "http"
    return {
        "name": bench_name,
        "port": port,
        "domain": domain,
        "production": production,
        "process_manager": process_manager or None,
        "reachable": bench.is_port_open(port) or bench.is_port_open(port + 1),
        "admin_url": f"{scheme}://{domain}" if domain else "",
        "workload_running": bench.is_workload_running if production else None,
        "admin_running": bench.is_admin_running if production else None,
        "site_count": bench.site_count,
    }


def _process_manager_name(value) -> str:
    if not isinstance(value, str):
        return ""
    process_manager = value.lower()
    if process_manager in ("", "none"):
        return ""
    if process_manager == "supervisord":
        return "supervisor"
    return process_manager


def resolve_bench_dir(benches_dir: Path, name: str) -> Path:
    """Resolve a bench by name under benches_dir, following symlinks to the real tree."""
    if not BENCH_NAME_RE.fullmatch(name):
        raise ValueError("Invalid bench path")
    entry = benches_dir / name
    if not entry.exists():
        raise ValueError("Invalid bench path")
    if entry.is_symlink():
        resolved = entry.resolve(strict=False)
        if not resolved.is_dir() or not (resolved / "bench.toml").is_file():
            raise ValueError("Invalid bench path")
        return resolved
    if entry.is_dir() and (entry / "bench.toml").is_file():
        return entry.resolve()
    raise ValueError("Invalid bench path")


def iter_bench_dirs(benches_dir: Path):
    """Each valid bench under benches_dir as (name, resolved_path)."""
    if not benches_dir.is_dir():
        return
    for entry in sorted(benches_dir.iterdir()):
        if not BENCH_NAME_RE.fullmatch(entry.name):
            continue
        try:
            yield entry.name, resolve_bench_dir(benches_dir, entry.name)
        except ValueError:
            continue


def target_bench_dir(bench_root: Path, name: str) -> Path:
    return resolve_bench_dir(bench_root.parent.resolve(), name)


def bench_lock_target(bench_root: Path, name: str) -> Path:
    return bench_root.parent / f"{name}.lifecycle"


def bench_management_lock_target(bench_root: Path) -> Path:
    return bench_root.parent / "bench-management.lock-target"


def bench_busy_response(name: str):
    return error_response(
        "bench_busy",
        f"Bench '{name}' is busy with another operation.",
        409,
    )
