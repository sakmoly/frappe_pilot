from pathlib import Path
from unittest.mock import patch

from pilot.core.site.data_clearing import SiteDataClearing, _execute_expression


def test_execute_expression_builds_importlib_call() -> None:
    expr = _execute_expression(Path("/opt/pilot"), "list_companies", None)
    assert "path.insert(0" in expr
    assert "list_companies()" in expr
    assert "pilot.integrations.erpnext.data_clearing" in expr


def test_execute_expression_uses_python_booleans() -> None:
    expr = _execute_expression(
        Path("/opt/pilot"),
        "start_clearing",
        {
            "company": "Acme",
            "clear_transactions": True,
            "clear_masters": False,
            "clear_chart_of_accounts": True,
            "included_apps": ["erpnext"],
            "excluded_doctypes": [],
        },
    )
    assert "'clear_transactions': True" in expr
    assert "'clear_masters': False" in expr


def test_list_companies_uses_importlib_execute(tmp_path) -> None:
    from types import SimpleNamespace

    bench = SimpleNamespace(
        python=Path("/usr/bin/python"),
        sites_path=tmp_path / "sites",
    )
    bench.sites_path.mkdir(parents=True)
    clearing = SiteDataClearing(bench, "site.localhost")

    with patch("pilot.core.site.data_clearing.subprocess.run") as run:
        run.return_value.returncode = 0
        run.return_value.stdout = '["Acme"]\n'
        run.return_value.stderr = ""
        result = clearing.list_companies()

    assert result == ["Acme"]
    command = run.call_args.args[0]
    assert command[-1].startswith("(lambda:")
    assert "list_companies()" in command[-1]
