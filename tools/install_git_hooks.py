"""Install repository-managed Git hooks for ReliabilityX Pro."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Sequence


HOOKS_PATH = ".githooks"


def _run_git(repo_root: Path, *args: str) -> str:
    """Run Git in the target repository.

    Args:
        repo_root: Repository root.
        *args: Git arguments.

    Returns:
        Stripped standard output.

    Raises:
        RuntimeError: If Git reports an error.
    """
    try:
        result = subprocess.run(
            ["git", "-c", f"safe.directory={repo_root.as_posix()}", *args],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        stderr = getattr(exc, "stderr", "") or ""
        raise RuntimeError(f"Git hook installation failed: {stderr.strip()}") from exc
    return result.stdout.strip()


def install_hooks(repo_root: Path | None = None) -> str:
    """Configure ``core.hooksPath`` and verify the result.

    Args:
        repo_root: Repository root. Defaults to the parent of ``tools``.

    Returns:
        The verified hooks path.

    Raises:
        RuntimeError: If the hook file is missing or configuration differs.
    """
    root = (repo_root or Path(__file__).resolve().parents[1]).resolve()
    hook_file = root / HOOKS_PATH / "pre-push"
    if not hook_file.is_file():
        raise RuntimeError(f"Managed pre-push hook is missing: {hook_file}")
    _run_git(root, "config", "core.hooksPath", HOOKS_PATH)
    configured = _run_git(root, "config", "--get", "core.hooksPath")
    if configured != HOOKS_PATH:
        raise RuntimeError(f"core.hooksPath verification failed: {configured!r}")
    return configured


def main(argv: Sequence[str] | None = None) -> int:
    """Install hooks for the current repository.

    Args:
        argv: Unused optional CLI arguments for a stable callable interface.

    Returns:
        Zero on success and non-zero on failure.
    """
    del argv
    try:
        configured = install_hooks()
        print(f"Git hooks enabled: core.hooksPath={configured}")
        return 0
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
