from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, ClassVar

from pilot.core.site import provision_from_backup
from pilot.exceptions import BenchError
from pilot.internal.site_paths import site_exists
from pilot.tasks import Arg, Task, step


@dataclass(kw_only=True)
class RestoreSiteTask(Task):
    command: ClassVar[str] = "restore-site"

    source_site: str
    target_site: str
    timestamp: str
    admin_password: Annotated[str | None, Arg(cli=False)] = None

    def run(self) -> None:
        self.restore()

    @step("restore", lambda self: f"Restore {self.target_site} from backup {self.timestamp}")
    def restore(self) -> None:
        db_file, public, private = self.bench.site(self.source_site).backups.paths_for_restore(
            self.timestamp
        )
        if site_exists(self.bench.path, self.target_site):
            site = self.bench.site(self.target_site)
            site.restore(db_file, public, private)
            site.clear_cache()
            return

        if not isinstance(self.admin_password, str) or not self.admin_password.strip():
            raise BenchError("Site Administrator password is required when restoring to a new site.")
        self.require_production_privileges()
        provision_from_backup(
            self.bench,
            self.target_site,
            db_file,
            admin_password=self.admin_password,
            public_files=public,
            private_files=private,
            on_progress=self.report,
        )


if __name__ == "__main__":
    RestoreSiteTask.main()
