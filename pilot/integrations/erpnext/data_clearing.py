"""Runs inside a site context via bench execute (PYTHONPATH must include the pilot repo)."""

from __future__ import annotations

import frappe
from frappe.modules.utils import get_doctype_module, get_module_app

from erpnext.setup.doctype.transaction_deletion_record.transaction_deletion_record import (
    get_doctypes_to_be_ignored,
    is_deletion_doc_running,
)

_MASTER_DOCTYPES = {
    "Account",
    "Cost Center",
    "Warehouse",
    "Budget",
    "Party Account",
    "Employee",
    "Sales Taxes and Charges Template",
    "Purchase Taxes and Charges Template",
    "POS Profile",
    "BOM",
    "Bank Account",
    "Item Tax Template",
    "Mode of Payment",
    "Mode of Payment Account",
    "Item Default",
    "Customer",
    "Supplier",
    "Department",
}


def list_companies() -> list[str]:
    frappe.only_for("System Manager")
    return frappe.get_all("Company", pluck="name", order_by="name")


def preview(company: str) -> dict:
    frappe.only_for("System Manager")
    if not frappe.db.exists("Company", company):
        frappe.throw(f"Company {company} does not exist.")
    if "erpnext" not in frappe.get_installed_apps():
        frappe.throw("ERPNext is not installed on this site.")

    ignored_for_category = set(get_doctypes_to_be_ignored())
    ignored_for_category.update(frappe.get_hooks("company_data_to_be_ignored") or [])

    apps: dict[str, dict] = {}
    for doctype in _company_doctypes(_protected_doctypes()):
        app = _doctype_app(doctype)
        count = frappe.db.count(doctype, _company_filter(doctype, company))
        if count == 0:
            continue
        bucket = apps.setdefault(app, {"app": app, "doctypes": [], "document_count": 0})
        bucket["doctypes"].append(
            {
                "doctype": doctype,
                "document_count": count,
                "category": _doctype_category(doctype, ignored_for_category),
            }
        )
        bucket["document_count"] += count

    return {
        "company": company,
        "apps": sorted(apps.values(), key=lambda row: row["app"]),
        "master_doctypes": sorted(_MASTER_DOCTYPES),
    }


def start_clearing(
    company: str,
    clear_transactions: bool = True,
    clear_masters: bool = False,
    clear_chart_of_accounts: bool = False,
    included_apps: list[str] | None = None,
    excluded_doctypes: list[str] | None = None,
) -> str:
    frappe.only_for("System Manager")
    if not clear_transactions:
        frappe.throw("Clearing transactions is required.")
    if "erpnext" not in frappe.get_installed_apps():
        frappe.throw("ERPNext is not installed on this site.")
    if not frappe.db.exists("Company", company):
        frappe.throw(f"Company {company} does not exist.")

    is_deletion_doc_running(company)

    tdr = frappe.get_doc({"doctype": "Transaction Deletion Record", "company": company})
    for doctype in _ignore_list(clear_masters, clear_chart_of_accounts):
        tdr.append("doctypes_to_be_ignored", {"doctype_name": doctype})

    tdr.insert()
    tdr.generate_to_delete_list()
    _apply_doctype_filters(tdr, included_apps, excluded_doctypes or [])
    if not tdr.doctypes_to_delete:
        frappe.throw("Nothing matched the selected apps and filters.")

    tdr.save()
    tdr.submit()
    return tdr.name


def deletion_status(tdr_name: str) -> dict:
    frappe.only_for("System Manager")
    if not frappe.db.exists("Transaction Deletion Record", tdr_name):
        frappe.throw(f"Transaction Deletion Record {tdr_name} was not found.")
    doc = frappe.get_doc("Transaction Deletion Record", tdr_name)
    return {
        "name": doc.name,
        "status": doc.status,
        "company": doc.company,
        "error_log": doc.error_log,
        "delete_transactions_status": doc.delete_transactions_status,
        "reset_company_default_values_status": doc.reset_company_default_values_status,
    }


def _ignore_list(clear_masters: bool, clear_chart_of_accounts: bool) -> list[str]:
    ignored = set(get_doctypes_to_be_ignored())
    ignored.update(frappe.get_hooks("company_data_to_be_ignored") or [])
    ignored.add("Company")
    if clear_masters:
        ignored -= _MASTER_DOCTYPES
    if clear_chart_of_accounts:
        ignored.discard("Account")
    return sorted(ignored)


def _protected_doctypes() -> set[str]:
    from erpnext.setup.doctype.transaction_deletion_record.transaction_deletion_record import (
        PROTECTED_CORE_DOCTYPES,
    )

    singles = set(frappe.get_all("DocType", filters={"issingle": 1}, pluck="name"))
    virtual = set(frappe.get_all("DocType", filters={"is_virtual": 1}, pluck="name"))
    return set(PROTECTED_CORE_DOCTYPES) | singles | virtual


def _company_doctypes(excluded: set[str]) -> list[str]:
    parents = set(
        frappe.get_all(
            "DocField",
            filters={"fieldtype": "Link", "options": "Company"},
            pluck="parent",
            distinct=True,
        )
    )
    valid = []
    for name in parents:
        if name in excluded or not frappe.db.exists("DocType", name):
            continue
        meta = frappe.get_meta(name)
        if meta.istable or meta.is_virtual:
            continue
        valid.append(name)
    return sorted(valid)


def _company_filter(doctype: str, company: str) -> dict:
    field = frappe.db.get_value(
        "DocField",
        {"parent": doctype, "fieldtype": "Link", "options": "Company"},
        "fieldname",
    )
    return {field or "company": company}


def _doctype_app(doctype: str) -> str:
    module = get_doctype_module(doctype)
    return get_module_app(module) or "frappe"


def _doctype_category(doctype: str, ignored: set[str]) -> str:
    if doctype in _MASTER_DOCTYPES or doctype in ignored:
        return "master"
    if doctype == "Account":
        return "chart_of_accounts"
    return "transaction"


def _apply_doctype_filters(tdr, included_apps: list[str] | None, excluded_doctypes: list[str]) -> None:
    excluded = set(excluded_doctypes)
    allowed_apps = set(included_apps) if included_apps else None
    to_remove = []
    for row in tdr.doctypes_to_delete:
        if row.doctype_name in excluded:
            to_remove.append(row)
            continue
        if allowed_apps is not None and _doctype_app(row.doctype_name) not in allowed_apps:
            to_remove.append(row)
    for row in to_remove:
        tdr.remove(row)
