"""Backup integrity, retention, exclusion, and pre-push gate tests."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

import tools.create_git_backup as backup_manager


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run Git against a temporary offline repository.

    Args:
        repo: Temporary repository path.
        *args: Git arguments.
        check: Whether non-zero status raises.

    Returns:
        Completed Git process.
    """
    # Hooks must use the same interpreter as pytest, including portable venvs.
    environment = dict(os.environ)
    environment["PATH"] = str(Path(sys.executable).parent) + os.pathsep + environment.get("PATH", "")
    return subprocess.run(
        ["git", "-c", f"safe.directory={repo.as_posix()}", *args],
        cwd=repo,
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
    )


def _init_repository(path: Path) -> str:
    """Create a temporary Git repository with tracked and ignored content."""
    path.mkdir(parents=True)
    _git(path, "init")
    _git(path, "branch", "-M", "main")
    _git(path, "config", "user.name", "Offline Test")
    _git(path, "config", "user.email", "offline@example.invalid")
    (path / ".gitignore").write_text("data/\nlogs/\n_local_only/\nBACKUP/\n.env\n", encoding="utf-8")
    (path / "source.py").write_text("VALUE = 1\n", encoding="utf-8")
    (path / "README.md").write_text("# Offline fixture\n", encoding="utf-8")
    for relative, content in (
        ("data/private.csv", "private"),
        ("logs/private.log", "private"),
        ("_local_only/manual.pdf", "private"),
        ("BACKUP/old.zip", "private"),
        (".env", "SECRET=private"),
    ):
        target = path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    _git(path, "add", ".gitignore", "source.py", "README.md")
    _git(path, "commit", "-m", "fixture")
    return _git(path, "rev-parse", "HEAD").stdout.strip()


@pytest.mark.offline
def test_backup_creation_filename_manifest_and_exclusions(tmp_path: Path) -> None:
    """A backup contains only tracked snapshot data plus the safe manifest."""
    repo = tmp_path / "repo with spaces"
    sha = _init_repository(repo)
    created = dt.datetime(2026, 8, 19, 20, 50, 12, tzinfo=backup_manager.TAIPEI_TIMEZONE)
    archive_path = backup_manager.create_backup(repo, now=created)
    assert re.fullmatch(rf"ReliabilityX_Pro_20260819_205012_{sha[:7]}\.zip", archive_path.name)
    with zipfile.ZipFile(archive_path) as archive:
        assert archive.testzip() is None
        names = set(archive.namelist())
        assert {"source.py", "README.md", ".gitignore", "BACKUP_MANIFEST.json"} <= names
        assert not any(name.startswith(".git/") for name in names)
        assert not any(name.startswith("data/") for name in names)
        assert not any(name.startswith("logs/") for name in names)
        assert not any(name.startswith("_local_only/") for name in names)
        assert not any(name.startswith("BACKUP/") for name in names)
        assert ".env" not in names
        manifest = json.loads(archive.read("BACKUP_MANIFEST.json"))
    assert manifest["commit_sha"] == sha
    assert manifest["short_sha"] == sha[:7]
    assert manifest["trigger"] == "manual"
    assert manifest["timezone"] == "Asia/Taipei"
    assert "username" not in manifest
    assert "email" not in manifest


@pytest.mark.offline
def test_retention_keeps_latest_ten_and_unrelated_files(tmp_path: Path) -> None:
    """Twelve project archives retain newest ten without deleting other files."""
    repo = tmp_path / "repo"
    _init_repository(repo)
    unrelated = repo / "BACKUP" / "README_local.txt"
    unrelated.write_text("keep", encoding="utf-8")
    base = dt.datetime(2026, 8, 19, 10, 0, 0, tzinfo=backup_manager.TAIPEI_TIMEZONE)
    created_names = []
    for index in range(12):
        created_names.append(backup_manager.create_backup(repo, now=base + dt.timedelta(seconds=index)).name)
    remaining = sorted(path.name for path in (repo / "BACKUP").glob("ReliabilityX_Pro_*.zip"))
    assert len(remaining) == 10
    assert created_names[0] not in remaining
    assert created_names[1] not in remaining
    assert set(created_names[2:]) == set(remaining)
    assert unrelated.read_text(encoding="utf-8") == "keep"


@pytest.mark.offline
def test_creation_failure_returns_nonzero_and_removes_temp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Filesystem/archive creation failure is push-blocking and leaves no temp."""
    repo = tmp_path / "repo"
    _init_repository(repo)

    def fail_archive(*args: object, **kwargs: object) -> None:
        """Simulate a permission failure."""
        del args, kwargs
        raise PermissionError("denied")

    monkeypatch.setattr(backup_manager, "_create_git_archive", fail_archive)
    assert backup_manager.main(["--repository", str(repo)]) == 1
    assert not list((repo / "BACKUP").glob("*.tmp"))
    assert not list((repo / "BACKUP").glob("ReliabilityX_Pro_*.zip"))
    assert (repo / "BACKUP" / "old.zip").is_file()


@pytest.mark.offline
def test_corruption_validation_failure_never_publishes_final_zip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed integrity check leaves neither final nor temporary archive."""
    repo = tmp_path / "repo"
    _init_repository(repo)

    def fail_validation(*args: object, **kwargs: object) -> tuple[int, int]:
        """Simulate ``ZipFile.testzip`` detecting corruption."""
        del args, kwargs
        raise backup_manager.BackupError("corrupt")

    monkeypatch.setattr(backup_manager, "_validate_archive", fail_validation)
    with pytest.raises(backup_manager.BackupError, match="corrupt"):
        backup_manager.create_backup(repo)
    assert not list((repo / "BACKUP").glob("*.tmp"))
    assert not list((repo / "BACKUP").glob("ReliabilityX_Pro_*.zip"))
    assert (repo / "BACKUP" / "old.zip").is_file()


@pytest.mark.offline
def test_pre_push_hook_allows_success_and_blocks_backup_failure(
    tmp_path: Path, repository_root: Path
) -> None:
    """Local bare remote proves backup success allows and failure blocks push."""
    repo = tmp_path / "working repo with spaces"
    remote = tmp_path / "remote.git"
    repo.mkdir(parents=True)
    _git(repo, "init")
    _git(repo, "branch", "-M", "main")
    _git(repo, "config", "user.name", "Offline Test")
    _git(repo, "config", "user.email", "offline@example.invalid")
    (repo / "tools").mkdir()
    (repo / ".githooks").mkdir()
    shutil.copy2(repository_root / "tools" / "create_git_backup.py", repo / "tools" / "create_git_backup.py")
    shutil.copy2(repository_root / ".githooks" / "pre-push", repo / ".githooks" / "pre-push")
    (repo / ".gitignore").write_text("/BACKUP/\n", encoding="utf-8")
    (repo / "source.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(repo, "add", ".gitignore", "source.py", "tools/create_git_backup.py", ".githooks/pre-push")
    _git(repo, "commit", "-m", "initial")
    _git(repo, "config", "core.hooksPath", ".githooks")
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True, text=True)
    _git(repo, "remote", "add", "origin", str(remote))

    success = _git(repo, "push", "origin", "main", check=False)
    assert success.returncode == 0, success.stderr
    first_remote_sha = _git(remote, "rev-parse", "refs/heads/main").stdout.strip()
    successful_archives = list((repo / "BACKUP").glob("ReliabilityX_Pro_*.zip"))
    assert successful_archives
    with zipfile.ZipFile(successful_archives[0]) as archive:
        manifest = json.loads(archive.read("BACKUP_MANIFEST.json"))
    assert manifest["trigger"] == "pre-push"
    assert manifest["commit_sha"] == first_remote_sha

    shutil.rmtree(repo / "BACKUP")
    (repo / "BACKUP").write_text("blocks directory creation", encoding="utf-8")
    (repo / "source.py").write_text("VALUE = 2\n", encoding="utf-8")
    _git(repo, "add", "source.py")
    _git(repo, "commit", "-m", "must be blocked")
    blocked = _git(repo, "push", "origin", "main", check=False)
    assert blocked.returncode != 0
    assert "Backup failed; Git push is blocked" in blocked.stderr
    assert _git(remote, "rev-parse", "refs/heads/main").stdout.strip() == first_remote_sha
