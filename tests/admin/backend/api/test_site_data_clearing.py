"""Tests for /api/v1/sites/<name>/data-clearing and clear-data action."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from pilot.config import BenchConfig


def _client(bench_root: Path, password: str = "secret"):
    from admin.backend.app import create_app
    from admin.backend.internal.session import Session
    from pilot.core.bench import Bench

    bench_root.mkdir(parents=True, exist_ok=True)
    (bench_root / "bench.toml").write_text(
        BenchConfig.from_flat(bench_root.name, {"admin_enabled": True, "admin_password": password}).dumps()
    )
    app = create_app(bench_root)
    app.config["TESTING"] = True
    client = app.test_client()
    client.set_cookie("sid", Session(Bench(bench_root)).issue_session_token()[0])
    return client


def _make_site(bench_root: Path, name: str, **config) -> None:
    site_dir = bench_root / "sites" / name
    site_dir.mkdir(parents=True)
    (site_dir / "site_config.json").write_text(json.dumps(config))


def _make_backup_file(bench_root: Path, site: str, timestamp: str, suffix: str) -> Path:
    backups_dir = bench_root / "sites" / site / "private" / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    path = backups_dir / f"{timestamp}-{site}-{suffix}"
    path.write_text("data")
    return path


def _request(client, method, path, **kwargs):
    with patch(
        "pilot.internal.tasks.runner.task_workers.wake",
        return_value=False,
    ):
        return getattr(client, method)(path, **kwargs)


def test_list_companies_returns_erpnext_error_without_erpnext(tmp_path: Path) -> None:
    bench_root = tmp_path / "benches" / "current"
    _make_site(bench_root, "site.localhost", installed_apps=["frappe"])
    client = _client(bench_root)

    with patch(
        "pilot.core.site.config.query_installed_apps_via_db",
        return_value=None,
    ), patch(
        "pilot.core.site.config.query_installed_apps_via_frappe",
        return_value=["frappe"],
    ):
        response = client.get("/api/v1/sites/site.localhost/data-clearing/companies")

    body = response.get_json()
    assert response.status_code == 422
    assert body["error"]["code"] == "erpnext_required"


def test_list_companies_allows_erpnext_from_frappe_when_config_is_stale(tmp_path: Path) -> None:
    bench_root = tmp_path / "benches" / "current"
    _make_site(bench_root, "site.localhost", installed_apps=["frappe"])
    client = _client(bench_root)

    with patch(
        "pilot.core.site.config.query_installed_apps_via_db",
        return_value=None,
    ), patch(
        "pilot.core.site.config.query_installed_apps_via_frappe",
        return_value=["frappe", "erpnext"],
    ), patch(
        "admin.backend.api.v1.sites.data_clearing.SiteDataClearing.list_companies",
        return_value=["Acme"],
    ):
        response = client.get("/api/v1/sites/site.localhost/data-clearing/companies")

    assert response.status_code == 200
    assert response.get_json() == ["Acme"]


def test_list_companies_returns_company_names(tmp_path: Path) -> None:
    bench_root = tmp_path / "benches" / "current"
    _make_site(bench_root, "site.localhost", installed_apps=["frappe", "erpnext"])
    client = _client(bench_root)

    with patch(
        "admin.backend.api.v1.sites.data_clearing.SiteDataClearing.list_companies",
        return_value=["Acme", "Beta"],
    ):
        response = client.get("/api/v1/sites/site.localhost/data-clearing/companies")

    assert response.status_code == 200
    assert response.get_json() == ["Acme", "Beta"]


def test_preview_requires_company(tmp_path: Path) -> None:
    bench_root = tmp_path / "benches" / "current"
    _make_site(bench_root, "site.localhost", installed_apps=["frappe", "erpnext"])
    client = _client(bench_root)

    response = client.get("/api/v1/sites/site.localhost/data-clearing/preview")

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "invalid_fields"


def test_preview_returns_app_counts(tmp_path: Path) -> None:
    bench_root = tmp_path / "benches" / "current"
    _make_site(bench_root, "site.localhost", installed_apps=["frappe", "erpnext"])
    client = _client(bench_root)
    preview = {
        "company": "Acme",
        "apps": [{"app": "erpnext", "document_count": 42, "doctypes": []}],
        "master_doctypes": ["Customer"],
    }

    with patch(
        "admin.backend.api.v1.sites.data_clearing.SiteDataClearing.preview",
        return_value=preview,
    ):
        response = client.get("/api/v1/sites/site.localhost/data-clearing/preview?company=Acme")

    assert response.status_code == 200
    assert response.get_json() == preview


def test_clear_data_requires_local_backup(tmp_path: Path) -> None:
    bench_root = tmp_path / "benches" / "current"
    _make_site(bench_root, "site.localhost", installed_apps=["frappe", "erpnext"])
    client = _client(bench_root)

    response = _request(
        client,
        "post",
        "/api/v1/sites/site.localhost/actions/clear-data",
        json={"company": "Acme"},
    )

    body = response.get_json()
    assert response.status_code == 422
    assert body["error"]["code"] == "backup_required"


def test_clear_data_queues_task(tmp_path: Path) -> None:
    bench_root = tmp_path / "benches" / "current"
    _make_site(bench_root, "site.localhost", installed_apps=["frappe", "erpnext"])
    _make_backup_file(bench_root, "site.localhost", "20240101_000000", "database.sql.gz")
    client = _client(bench_root)

    response = _request(
        client,
        "post",
        "/api/v1/sites/site.localhost/actions/clear-data",
        json={
            "company": "Acme",
            "clear_masters": True,
            "included_apps": ["erpnext", "printechs_wms"],
        },
    )

    body = response.get_json()
    assert response.status_code == 202
    assert body["command"] == "clear-site-data"
    assert body["args"] == {
        "site": "site.localhost",
        "company": "Acme",
        "clear_transactions": True,
        "clear_masters": True,
        "clear_chart_of_accounts": False,
        "included_apps": ["erpnext", "printechs_wms"],
        "excluded_doctypes": [],
    }
