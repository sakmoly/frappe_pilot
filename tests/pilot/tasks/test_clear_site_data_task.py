from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from pilot.exceptions import BenchError
from pilot.tasks.clear_site_data import ClearSiteDataTask


def _bench(tmp_path):
    bench_root = tmp_path
    (bench_root / "sites").mkdir()
    site = SimpleNamespace(clear_cache=MagicMock())
    return SimpleNamespace(
        path=bench_root,
        sites_path=bench_root / "sites",
        site=lambda name: site,
    )


def test_clear_site_data_task_runs_clearing(tmp_path) -> None:
    bench = _bench(tmp_path)
    task = ClearSiteDataTask(
        bench=bench,
        bench_root=tmp_path,
        site="site.localhost",
        company="Acme",
        clear_masters=True,
        included_apps=["erpnext"],
    )
    clearing = MagicMock()
    clearing.start.return_value = "TDR-0001"
    clearing.wait_for_completion.return_value = {"status": "Completed", "name": "TDR-0001"}

    with patch("pilot.tasks.clear_site_data.SiteDataClearing", return_value=clearing):
        task.run()

    clearing.start.assert_called_once()
    clearing.wait_for_completion.assert_called_once_with("TDR-0001", task.report)
    bench.site("site.localhost").clear_cache.assert_called_once()


def test_clear_site_data_task_requires_transactions(tmp_path) -> None:
    bench = _bench(tmp_path)
    task = ClearSiteDataTask(
        bench=bench,
        bench_root=tmp_path,
        site="site.localhost",
        company="Acme",
        clear_transactions=False,
    )

    with pytest.raises(BenchError, match="Clearing transactions is required"):
        task.run()


def test_clear_site_data_task_passes_options(tmp_path) -> None:
    bench = _bench(tmp_path)
    task = ClearSiteDataTask(
        bench=bench,
        bench_root=tmp_path,
        site="site.localhost",
        company="Acme",
        clear_chart_of_accounts=True,
        included_apps=["erpnext"],
    )
    captured = {}

    class Clearing:
        def start(self, company, options):
            captured["company"] = company
            captured["options"] = options
            return "TDR-0002"

        def wait_for_completion(self, tdr_name, on_progress):
            return {"status": "Completed"}

    with patch("pilot.tasks.clear_site_data.SiteDataClearing", return_value=Clearing()):
        task.run()

    assert captured["company"] == "Acme"
    assert captured["options"]["clear_chart_of_accounts"] is True
    assert captured["options"]["included_apps"] == ["erpnext"]
