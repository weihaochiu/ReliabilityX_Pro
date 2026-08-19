"""Create validated local backups of committed Git source snapshots.

The archive source is a Git commit, not the working tree. This guarantees that
ignored runtime data, local configuration, credentials, ``.git``, ``BACKUP``,
and ``_local_only`` are absent unless they were intentionally tracked.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import urllib.parse
import zipfile
from pathlib import Path
from typing import Sequence


PROJECT_NAME = "ReliabilityX Pro"
ARCHIVE_PREFIX = "ReliabilityX_Pro"
MANIFEST_NAME = "BACKUP_MANIFEST.json"
RETENTION_LIMIT = 10
TAIPEI_TIMEZONE = dt.timezone(dt.timedelta(hours=8), name="Asia/Taipei")
BACKUP_PATTERN = re.compile(
    r"^ReliabilityX_Pro_(?P<date>\d{8})_(?P<time>\d{6})_"
    r"(?P<sha>[0-9a-fA-F]{7,40})\.zip$"
)


class BackupError(RuntimeError):
    """Raised when a backup cannot be created or validated safely."""


def _run_git(repo_root: Path, *args: str) -> str:
    """Run one Git command and return stripped stdout.

    Args:
        repo_root: Repository working-tree root.
        *args: Git command arguments.

    Returns:
        The command standard output without surrounding whitespace.

    Raises:
        BackupError: If Git cannot execute the requested command.
    """
    command = ["git", "-c", f"safe.directory={repo_root.as_posix()}", *args]
    try:
        result = subprocess.run(
            command,
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        stderr = getattr(exc, "stderr", "") or ""
        raise BackupError(f"Git command failed: {' '.join(args)} | {stderr.strip()}") from exc
    return result.stdout.strip()


def find_repository_root(start: Path | None = None) -> Path:
    """Locate the Git repository containing ``start``.

    Args:
        start: Path from which to locate the repository.

    Returns:
        Resolved repository root.

    Raises:
        BackupError: If the path is not inside a Git working tree.
    """
    candidate = (start or Path.cwd()).resolve()
    try:
        result = subprocess.run(
            ["git", "-c", f"safe.directory={candidate.as_posix()}", "rev-parse", "--show-toplevel"],
            cwd=candidate,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise BackupError(f"Not a Git repository: {candidate}") from exc
    return Path(result.stdout.strip()).resolve()


def _validate_commit_sha(repo_root: Path, commit: str | None) -> str:
    """Resolve and validate the commit that will be archived.

    Args:
        repo_root: Repository root.
        commit: Optional commit-ish supplied by the pre-push hook.

    Returns:
        Full 40-character commit SHA.

    Raises:
        BackupError: If the object is not a commit.
    """
    commitish = str(commit or "HEAD").strip()
    sha = _run_git(repo_root, "rev-parse", "--verify", f"{commitish}^{{commit}}")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", sha):
        raise BackupError(f"Invalid commit SHA returned by Git: {sha!r}")
    return sha.lower()


def _sanitize_remote_url(remote: str) -> str:
    """Remove URL credentials and query fragments from a remote value.

    Args:
        remote: Git remote URL.

    Returns:
        A non-secret remote identifier suitable for the backup manifest.
    """
    value = str(remote or "").strip()
    if not value:
        return ""
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme and parsed.netloc:
        host = parsed.hostname or ""
        if parsed.port:
            host = f"{host}:{parsed.port}"
        return urllib.parse.urlunsplit((parsed.scheme, host, parsed.path, "", ""))
    return value.split("?", 1)[0].split("#", 1)[0]


def _build_manifest(repo_root: Path, commit_sha: str, trigger: str, created_at: dt.datetime) -> dict[str, object]:
    """Build a privacy-safe archive manifest.

    Args:
        repo_root: Repository root.
        commit_sha: Full commit SHA being archived.
        trigger: ``manual`` or ``pre-push``.
        created_at: Timezone-aware creation timestamp.

    Returns:
        JSON-serializable manifest dictionary.
    """
    branch = _run_git(repo_root, "branch", "--show-current")
    remote = ""
    try:
        remote = _sanitize_remote_url(_run_git(repo_root, "remote", "get-url", "origin"))
    except BackupError:
        remote = ""
    tracked_raw = _run_git(repo_root, "ls-tree", "-r", "--name-only", commit_sha)
    tracked_count = len([line for line in tracked_raw.splitlines() if line.strip()])
    try:
        describe = _run_git(repo_root, "describe", "--tags", "--always", commit_sha)
    except BackupError:
        describe = commit_sha[:7]
    return {
        "project": PROJECT_NAME,
        "created_at": created_at.isoformat(timespec="seconds"),
        "timezone": "Asia/Taipei",
        "branch": branch,
        "commit_sha": commit_sha,
        "short_sha": commit_sha[:7],
        "remote": remote,
        "trigger": trigger,
        "archive_type": "git-tracked-source-snapshot",
        "git_describe": describe,
        "tracked_file_count": tracked_count,
    }


def _create_git_archive(repo_root: Path, commit_sha: str, temp_path: Path) -> None:
    """Write a Git-tracked ZIP snapshot to a temporary path.

    Args:
        repo_root: Repository root.
        commit_sha: Commit to archive.
        temp_path: Temporary output path.

    Raises:
        BackupError: If ``git archive`` fails.
    """
    command = [
        "git",
        "-c",
        f"safe.directory={repo_root.as_posix()}",
        "archive",
        "--format=zip",
        f"--output={temp_path}",
        commit_sha,
    ]
    try:
        subprocess.run(
            command,
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        stderr = getattr(exc, "stderr", "") or ""
        raise BackupError(f"git archive failed: {stderr.strip()}") from exc


def _append_manifest(temp_path: Path, manifest: dict[str, object]) -> None:
    """Append ``BACKUP_MANIFEST.json`` to a temporary ZIP.

    Args:
        temp_path: Temporary ZIP path.
        manifest: Manifest payload.

    Raises:
        BackupError: If the manifest already exists or cannot be written.
    """
    try:
        with zipfile.ZipFile(temp_path, mode="a", compression=zipfile.ZIP_DEFLATED) as archive:
            if MANIFEST_NAME in archive.namelist():
                raise BackupError(f"Tracked snapshot already contains reserved file {MANIFEST_NAME}")
            payload = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            archive.writestr(MANIFEST_NAME, payload.encode("utf-8"))
    except BackupError:
        raise
    except (OSError, zipfile.BadZipFile) as exc:
        raise BackupError(f"Unable to add backup manifest: {exc}") from exc


def _validate_archive(temp_path: Path, commit_sha: str) -> tuple[int, int]:
    """Validate ZIP integrity, manifest identity, and non-empty contents.

    Args:
        temp_path: ZIP to validate.
        commit_sha: Expected commit SHA.

    Returns:
        Tuple of archive member count and archive size in bytes.

    Raises:
        BackupError: If any integrity or identity check fails.
    """
    try:
        if not temp_path.is_file() or temp_path.stat().st_size <= 0:
            raise BackupError("Backup ZIP is missing or empty")
        with zipfile.ZipFile(temp_path, mode="r") as archive:
            corrupt_member = archive.testzip()
            if corrupt_member is not None:
                raise BackupError(f"ZIP integrity failure at member: {corrupt_member}")
            names = archive.namelist()
            if MANIFEST_NAME not in names:
                raise BackupError(f"{MANIFEST_NAME} is missing")
            manifest = json.loads(archive.read(MANIFEST_NAME).decode("utf-8"))
            if manifest.get("commit_sha") != commit_sha:
                raise BackupError("Backup manifest commit SHA does not match archive request")
            if len(names) <= 1:
                raise BackupError("Backup contains no tracked source files")
        return len(names), temp_path.stat().st_size
    except BackupError:
        raise
    except (OSError, zipfile.BadZipFile, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise BackupError(f"Backup validation failed: {exc}") from exc


def enforce_retention(backup_dir: Path, limit: int = RETENTION_LIMIT) -> list[Path]:
    """Delete only the oldest matching project archives beyond ``limit``.

    Args:
        backup_dir: Directory containing local backups.
        limit: Maximum number of matching backups to retain.

    Returns:
        Paths removed from oldest to newest.

    Raises:
        BackupError: If matching archives cannot be enumerated or removed.
    """
    try:
        matching = [path for path in backup_dir.iterdir() if path.is_file() and BACKUP_PATTERN.fullmatch(path.name)]
        matching.sort(key=lambda path: (BACKUP_PATTERN.fullmatch(path.name).group("date"), BACKUP_PATTERN.fullmatch(path.name).group("time"), path.stat().st_mtime_ns, path.name))
        to_remove = matching[: max(0, len(matching) - max(0, int(limit)))]
        for path in to_remove:
            path.unlink()
        remaining = [path for path in backup_dir.iterdir() if path.is_file() and BACKUP_PATTERN.fullmatch(path.name)]
        if len(remaining) > max(0, int(limit)):
            raise BackupError(f"Retention verification failed: {len(remaining)} matching backups remain")
        return to_remove
    except BackupError:
        raise
    except OSError as exc:
        raise BackupError(f"Backup retention failed: {exc}") from exc


def create_backup(
    repo_root: Path | None = None,
    *,
    backup_dir: Path | None = None,
    trigger: str = "manual",
    commit: str | None = None,
    now: dt.datetime | None = None,
) -> Path:
    """Create, validate, atomically publish, and retain a Git snapshot.

    Args:
        repo_root: Repository root or a path inside it.
        backup_dir: Optional backup directory override, primarily for tests.
        trigger: ``manual`` or ``pre-push``.
        commit: Optional commit SHA supplied by Git's pre-push hook.
        now: Optional timezone-aware creation time for deterministic tests.

    Returns:
        Final validated ZIP path.

    Raises:
        BackupError: If creation, validation, atomic rename, or retention fails.
    """
    if trigger not in {"manual", "pre-push"}:
        raise BackupError(f"Unsupported backup trigger: {trigger}")
    root = find_repository_root(repo_root) if repo_root is not None else find_repository_root()
    commit_sha = _validate_commit_sha(root, commit)
    created_at = now or dt.datetime.now(TAIPEI_TIMEZONE)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=TAIPEI_TIMEZONE)
    else:
        created_at = created_at.astimezone(TAIPEI_TIMEZONE)

    target_dir = (backup_dir or (root / "BACKUP")).resolve()
    timestamp = created_at.strftime("%Y%m%d_%H%M%S")
    final_path = target_dir / f"{ARCHIVE_PREFIX}_{timestamp}_{commit_sha[:7]}.zip"
    temp_path = target_dir / f".{final_path.name}.tmp"

    print(f"[BACKUP] Creating {trigger} snapshot...")
    print(f"[BACKUP] Commit: {commit_sha}")
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        if temp_path.exists():
            temp_path.unlink()
        manifest = _build_manifest(root, commit_sha, trigger, created_at)
        _create_git_archive(root, commit_sha, temp_path)
        _append_manifest(temp_path, manifest)
        member_count, archive_size = _validate_archive(temp_path, commit_sha)
        os.replace(temp_path, final_path)
        removed = enforce_retention(target_dir, RETENTION_LIMIT)
        current_count = len([path for path in target_dir.iterdir() if path.is_file() and BACKUP_PATTERN.fullmatch(path.name)])
        print(f"[BACKUP] Archive: {final_path}")
        print(f"[BACKUP] Integrity: PASS ({member_count} files, {archive_size} bytes)")
        print(f"[BACKUP] Retention: latest {RETENTION_LIMIT} (current {current_count}, removed {len(removed)})")
        print("[BACKUP] Backup completed successfully")
        return final_path
    except Exception as exc:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except OSError:
            pass
        if isinstance(exc, BackupError):
            raise
        raise BackupError(f"Backup creation failed: {exc}") from exc


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser.

    Returns:
        Configured argument parser.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trigger", choices=("manual", "pre-push"), default="manual")
    parser.add_argument("--repository", type=Path, default=None)
    parser.add_argument("--commit", default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the backup command and expose a push-blocking exit code.

    Args:
        argv: Optional command-line arguments.

    Returns:
        Zero on success; non-zero on any backup or retention failure.
    """
    args = build_argument_parser().parse_args(argv)
    try:
        create_backup(args.repository, trigger=args.trigger, commit=args.commit)
        return 0
    except BackupError as exc:
        print(f"[BACKUP] ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
