from __future__ import annotations

from pathlib import Path

from flask import current_app, jsonify, request

from admin.backend.api.responses import accepted_task_response, error_response
from admin.backend.api.v1.sites import sites_bp
from admin.backend.api.v1.sites.shared import (
    internal_error,
    invalid_fields,
    malformed_body,
    site_name,
    site_not_found,
    task_failure,
)
from admin.backend.middleware import require_scope
from admin.backend.providers.backups import BackupProvider
from pilot.core.bench import Bench
from pilot.core.site.data_clearing import SiteDataClearing
from pilot.exceptions import BenchError
from pilot.internal.site_paths import site_exists
from pilot.tasks.clear_site_data import ClearSiteDataTask


def _has_local_database_backup(bench_root: Path, site_name: str) -> bool:
    for backup in BackupProvider(bench_root, site_name).get_all(limit=20):
        if backup.is_offsite:
            continue
        if any(file.kind == "database" and file.path for file in backup.files):
            return True
    return False


def _erpnext_installed(bench_root: Path, site_name: str) -> bool:
    from pilot.core.site.config import query_installed_apps_via_db, query_installed_apps_via_frappe

    for source in (
        query_installed_apps_via_db(bench_root, site_name),
        query_installed_apps_via_frappe(bench_root, site_name),
        _installed_apps_from_site_config(bench_root, site_name),
    ):
        if source and "erpnext" in source:
            return True
    return False


def _installed_apps_from_site_config(bench_root: Path, site_name: str) -> list[str] | None:
    import json

    from pilot.internal.site_paths import resolve_site_path

    site_path = resolve_site_path(bench_root, site_name)
    if site_path is None:
        return None
    config_path = site_path / "site_config.json"
    try:
        config = json.loads(config_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    installed = config.get("installed_apps")
    return installed if isinstance(installed, list) else None


@sites_bp.get("/<name>/data-clearing/companies")
@require_scope(site_name)
def list_data_clearing_companies(name: str):
    bench_root = Path(current_app.config["BENCH_ROOT"])
    if not site_exists(bench_root, name):
        return site_not_found()
    if not _erpnext_installed(bench_root, name):
        return error_response("erpnext_required", "ERPNext is not installed on this site.", 422)
    try:
        companies = SiteDataClearing(Bench(bench_root), name).list_companies()
    except BenchError as error:
        return error_response("data_clearing_unavailable", str(error), 422)
    except Exception:
        return internal_error("Could not list companies for data clearing.")
    return jsonify(companies)


@sites_bp.get("/<name>/data-clearing/preview")
@require_scope(site_name)
def preview_data_clearing(name: str):
    bench_root = Path(current_app.config["BENCH_ROOT"])
    if not site_exists(bench_root, name):
        return site_not_found()
    company = request.args.get("company", "").strip()
    if not company:
        return invalid_fields()
    if not _erpnext_installed(bench_root, name):
        return error_response("erpnext_required", "ERPNext is not installed on this site.", 422)
    try:
        preview = SiteDataClearing(Bench(bench_root), name).preview(company)
    except BenchError as error:
        return error_response("data_clearing_unavailable", str(error), 422)
    except Exception:
        return internal_error("Could not preview data clearing.")
    return jsonify(preview)


@sites_bp.post("/<name>/actions/clear-data")
@require_scope(site_name)
def clear_site_data(name: str):
    bench_root = Path(current_app.config["BENCH_ROOT"])
    if not site_exists(bench_root, name):
        return site_not_found()
    if not _erpnext_installed(bench_root, name):
        return error_response("erpnext_required", "ERPNext is not installed on this site.", 422)
    if not _has_local_database_backup(bench_root, name):
        return error_response(
            "backup_required",
            "Take a local database backup before clearing site data.",
            422,
        )

    data = request.get_json(silent=True)
    if data is None:
        data = {}
    elif not isinstance(data, dict):
        return malformed_body()

    company = data.get("company")
    if not isinstance(company, str) or not company.strip():
        return invalid_fields()
    company = company.strip()

    clear_transactions = data.get("clear_transactions", True)
    clear_masters = bool(data.get("clear_masters"))
    clear_chart_of_accounts = bool(data.get("clear_chart_of_accounts"))
    if not clear_transactions:
        return error_response(
            "clear_transactions_required",
            "Clearing transactions is required.",
            422,
        )

    included_apps = data.get("included_apps")
    if included_apps is not None:
        if not isinstance(included_apps, list) or not all(isinstance(app, str) for app in included_apps):
            return invalid_fields()
        included_apps = [app.strip() for app in included_apps if app.strip()]
        if not included_apps:
            return invalid_fields()

    excluded_doctypes = data.get("excluded_doctypes")
    if excluded_doctypes is not None:
        if not isinstance(excluded_doctypes, list) or not all(
            isinstance(doctype, str) for doctype in excluded_doctypes
        ):
            return invalid_fields()
        excluded_doctypes = [doctype.strip() for doctype in excluded_doctypes if doctype.strip()]
    else:
        excluded_doctypes = []

    try:
        task_id = ClearSiteDataTask.queue(
            Bench(bench_root),
            site=name,
            company=company,
            clear_transactions=clear_transactions,
            clear_masters=clear_masters,
            clear_chart_of_accounts=clear_chart_of_accounts,
            included_apps=included_apps,
            excluded_doctypes=excluded_doctypes,
            idempotency_key=request.headers.get("Idempotency-Key"),
            resource_key=f"site:{name.lower()}",
        )
    except Exception as error:
        return task_failure(error)
    return accepted_task_response(bench_root, task_id)
