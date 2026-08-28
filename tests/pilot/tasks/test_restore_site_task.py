from types import SimpleNamespace
from unittest.mock import patch

import pytest

from pilot.config import SiteConfig
from pilot.core.site import Site
from pilot.core.site.backups import SiteBackups
from pilot.exceptions import BenchError
from pilot.tasks.restore_site import RestoreSiteTask


def _bench(tmp_path):
    bench_root = tmp_path
    (bench_root / "sites").mkdir()
    bench = SimpleNamespace(
        path=bench_root,
        sites_path=bench_root / "sites",
        config=SimpleNamespace(db_type="mariadb", s3=SimpleNamespace(is_configured=False)),
    )

    def make_site(name: str) -> Site:
        site = Site(SiteConfig(name=name, apps=[]), bench)
        site.path.mkdir(parents=True, exist_ok=True)
        return site

    bench.site = make_site
    return bench


def _site(tmp_path, name: str = "site1") -> Site:
    return _bench(tmp_path).site(name)


def test_paths_for_restore_returns_local_files(tmp_path) -> None:
    site = _site(tmp_path, "site.localhost")
    backups = site.path / "private" / "backups"
    backups.mkdir(parents=True)
    db = backups / "20240101_000000-site.localhost-database.sql.gz"
    public = backups / "20240101_000000-site.localhost-files.tar"
    private = backups / "20240101_000000-site.localhost-private-files.tar"
    db.write_text("db")
    public.write_text("public")
    private.write_text("private")

    database, public_path, private_path = SiteBackups(site).paths_for_restore("20240101_000000")

    assert database == str(db)
    assert public_path == str(public)
    assert private_path == str(private)


def test_paths_for_restore_rejects_offsite_only_backup(tmp_path) -> None:
    site = _site(tmp_path, "site.localhost")

    with pytest.raises(BenchError, match="not available locally"):
        SiteBackups(site).paths_for_restore("20240101_000000")


def test_restore_site_task_restores_existing_target(tmp_path) -> None:
    bench = _bench(tmp_path)
    backups = tmp_path / "sites" / "source.localhost" / "private" / "backups"
    backups.mkdir(parents=True)
    db = backups / "20240101_000000-source.localhost-database.sql.gz"
    db.write_text("db")
    bench.site("source.localhost")
    bench.site("target.localhost")

    task = RestoreSiteTask(
        bench=bench,
        bench_root=tmp_path,
        source_site="source.localhost",
        target_site="target.localhost",
        timestamp="20240101_000000",
    )

    with (
        patch("pilot.tasks.restore_site.site_exists", return_value=True),
        patch.object(Site, "restore") as restore,
        patch.object(Site, "clear_cache") as clear_cache,
    ):
        task.run()

    restore.assert_called_once_with(str(db), None, None)
    clear_cache.assert_called_once()


def test_restore_site_task_provisions_new_target(tmp_path) -> None:
    bench = _bench(tmp_path)
    backups = tmp_path / "sites" / "source.localhost" / "private" / "backups"
    backups.mkdir(parents=True)
    db = backups / "20240101_000000-source.localhost-database.sql.gz"
    db.write_text("db")
    bench.site("source.localhost")

    task = RestoreSiteTask(
        bench=bench,
        bench_root=tmp_path,
        source_site="source.localhost",
        target_site="new.localhost",
        timestamp="20240101_000000",
        admin_password="secret",
    )

    with (
        patch("pilot.tasks.restore_site.site_exists", return_value=False),
        patch.object(RestoreSiteTask, "require_production_privileges"),
        patch("pilot.tasks.restore_site.provision_from_backup") as provision,
    ):
        task.run()

    provision.assert_called_once()
    assert provision.call_args.kwargs["name"] == "new.localhost"
    assert provision.call_args.kwargs["db_file"] == str(db)
