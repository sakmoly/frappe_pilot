from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from pilot.core.site.data_clearing import SiteDataClearing
from pilot.exceptions import BenchError
from pilot.tasks import Task, step


@dataclass(kw_only=True)
class ClearSiteDataTask(Task):
    command: ClassVar[str] = "clear-site-data"

    site: str
    company: str
    clear_transactions: bool = True
    clear_masters: bool = False
    clear_chart_of_accounts: bool = False
    included_apps: list[str] | None = None
    excluded_doctypes: list[str] | None = None

    def run(self) -> None:
        if not self.clear_transactions:
            raise BenchError("Clearing transactions is required.")
        self.clear_data()

    @step("clear", lambda self: f"Clear data for {self.company} on {self.site}")
    def clear_data(self) -> None:
        clearing = SiteDataClearing(self.bench, self.site)
        options = {
            "clear_transactions": self.clear_transactions,
            "clear_masters": self.clear_masters,
            "clear_chart_of_accounts": self.clear_chart_of_accounts,
            "included_apps": self.included_apps,
            "excluded_doctypes": self.excluded_doctypes or [],
        }
        tdr_name = clearing.start(self.company, options)
        clearing.wait_for_completion(tdr_name, self.report)
        self.bench.site(self.site).clear_cache()


if __name__ == "__main__":
    ClearSiteDataTask.main()
