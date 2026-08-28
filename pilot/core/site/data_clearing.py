from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

from pilot.exceptions import BenchError

if TYPE_CHECKING:
    from pilot.core.bench import Bench

_EXECUTE_TIMEOUT = 120
_POLL_INTERVAL = 5
_MAX_WAIT = 4 * 60 * 60
_MODULE = "pilot.integrations.erpnext.data_clearing"


class SiteDataClearing:
    def __init__(self, bench: "Bench", site: str) -> None:
        self.bench = bench
        self.site = site

    def list_companies(self) -> list[str]:
        return self._execute("list_companies")

    def preview(self, company: str) -> dict:
        return self._execute("preview", {"company": company})

    def start(self, company: str, options: dict) -> str:
        payload = {
            "company": company,
            "clear_transactions": bool(options.get("clear_transactions", True)),
            "clear_masters": bool(options.get("clear_masters")),
            "clear_chart_of_accounts": bool(options.get("clear_chart_of_accounts")),
            "included_apps": options.get("included_apps"),
            "excluded_doctypes": options.get("excluded_doctypes") or [],
        }
        return self._execute("start_clearing", payload)

    def wait_for_completion(self, tdr_name: str, on_progress) -> dict:
        deadline = time.monotonic() + _MAX_WAIT
        while time.monotonic() < deadline:
            status = self._execute("deletion_status", {"tdr_name": tdr_name})
            on_progress(f"Transaction deletion {status['status']} ({tdr_name})")
            if status["status"] in {"Completed", "Failed", "Cancelled"}:
                if status["status"] != "Completed":
                    detail = status.get("error_log") or status["status"]
                    raise BenchError(f"Data clearing failed: {detail}")
                return status
            time.sleep(_POLL_INTERVAL)
        raise BenchError(f"Data clearing timed out waiting for {tdr_name}.")

    def _execute(self, method: str, kwargs: dict | None = None) -> dict | list | str:
        command = [
            str(self.bench.python),
            "-m",
            "frappe.utils.bench_helper",
            "frappe",
            "--site",
            self.site,
            "execute",
            _execute_expression(_pilot_root(), method, kwargs),
        ]

        env = os.environ.copy()
        env.pop("PYTHONPATH", None)

        try:
            result = subprocess.run(
                command,
                cwd=self.bench.sites_path,
                capture_output=True,
                text=True,
                timeout=_EXECUTE_TIMEOUT if method != "deletion_status" else 30,
                env=env,
            )
        except subprocess.TimeoutExpired as error:
            raise BenchError(f"Timed out running {method} on {self.site}.") from error

        if result.returncode != 0:
            message = (result.stderr or result.stdout or "").strip() or f"{method} failed"
            raise BenchError(message)

        output = (result.stdout or "").strip()
        if not output:
            return {}
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            if output.startswith('"') and output.endswith('"'):
                return json.loads(output)
            return output


def _execute_expression(pilot_root: Path, method: str, kwargs: dict | None) -> str:
    root = repr(str(pilot_root))
    call = f"__import__('importlib').import_module('{_MODULE}').{method}"
    if kwargs is not None:
        call += f"(**{repr(kwargs)})"
    else:
        call += "()"
    return f"(lambda: (__import__('sys').path.insert(0, {root}), {call})[1])()"


def _pilot_root() -> Path:
    import pilot

    return Path(pilot.__file__).resolve().parent.parent
