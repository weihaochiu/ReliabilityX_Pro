# ADR 0060: Repository-Managed Atomic Pre-Push Source Backups

- **Status:** Accepted
- **Date:** 2026-08-19
- **Scope:** `.githooks/pre-push`, `tools/create_git_backup.py`, `tools/install_git_hooks.py`, `BACKUP/`, `.gitignore`

## Context

ReliabilityX Pro requires a recoverable source snapshot before GitHub changes, but copying the whole working directory would capture `.git`, scientific data, logs, local manuals, live hardware configuration, credentials, caches, and prior backups. Git hooks are not activated automatically by clone, and a post-push backup would be too late to protect the remote update.

## Decision

1. The tracked `.githooks/pre-push` hook invokes the Python backup manager before Git permits a push. It uses the local commit SHA supplied on pre-push stdin; failure exits 1 and blocks the remote update.
2. `tools/create_git_backup.py` uses `git archive <commit>` as the source of truth. The snapshot therefore represents the exact committed, Git-tracked source being pushed rather than the mutable working tree.
3. Archives are written to ignored local `BACKUP/` using a hidden `.tmp`, extended with a privacy-safe `BACKUP_MANIFEST.json`, validated using `ZipFile.testzip()`, and atomically renamed only after integrity and commit identity checks pass.
4. Archive names use Asia/Taipei local time and the format `ReliabilityX_Pro_YYYYMMDD_HHMMSS_<SHORT_SHA>.zip`.
5. Retention considers only names matching the ReliabilityX Pro archive pattern. It keeps the latest 10 and never deletes unrelated files. Creation, validation, or retention uncertainty is an error and blocks push.
6. `tools/install_git_hooks.py` configures and verifies `core.hooksPath=.githooks`. Fresh clones must run this installer once.
7. The hook supports `python` with a `py -3` fallback and quotes the repository path for Git for Windows paths containing spaces. `--no-verify` and force push are not part of the supported workflow.

## Consequences

- GitHub cannot be updated through the normal repository workflow unless a validated local source backup succeeds first.
- ZIPs naturally exclude ignored/local content such as `.git`, `BACKUP`, `_local_only`, data, logs, caches, live configuration, and secrets.
- Only tracked committed content is protected; uncommitted working-tree changes are intentionally outside this backup definition.
- Local bare-remote integration tests prove success allows a push and induced backup failure leaves remote HEAD unchanged.
