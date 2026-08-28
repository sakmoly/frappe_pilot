from __future__ import annotations

from pilot.config.bench import (
    FRAMEWORK_BRANCHES,
    BenchConfig,
    default_python_for_framework_branch,
)


def test_framework_branches_include_version_15() -> None:
    assert "version-15" in FRAMEWORK_BRANCHES
    assert FRAMEWORK_BRANCHES.index("version-16") < FRAMEWORK_BRANCHES.index("version-15")


def test_default_python_for_framework_branch() -> None:
    assert default_python_for_framework_branch("version-16") == "3.14"
    assert default_python_for_framework_branch("version-15") == "3.11"
    assert default_python_for_framework_branch("version-15-hotfix") == "3.11"
    assert default_python_for_framework_branch("develop") == "3.14"
    assert default_python_for_framework_branch("custom") == "3.14"


def test_write_flat_syncs_python_when_app_branch_changes(tmp_path) -> None:
    BenchConfig.write_flat(tmp_path, "v15-bench", {"admin_password": "secret", "app_branch": "version-15"})

    config = BenchConfig.read(tmp_path)
    assert config.framework_app.branch == "version-15"
    assert config.python_version == "3.11"


def test_write_flat_version_16_keeps_python_3_14(tmp_path) -> None:
    BenchConfig.write_flat(tmp_path, "v16-bench", {"admin_password": "secret", "app_branch": "version-16"})

    assert BenchConfig.read(tmp_path).python_version == "3.14"
