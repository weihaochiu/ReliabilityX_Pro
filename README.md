# ReliabilityX Pro

ReliabilityX Pro is a Windows/Python scientific measurement application for photovoltaic reliability experiments. It coordinates an SMU, relay paths, environmental equipment, measurement scheduling, analysis, logging, and reporting.

> Hardware safety: do not run hardware-connected validation unless the station, DUT, relay map, compliance limits, and emergency-stop procedure have been reviewed by a qualified operator. Repository baseline checks are intentionally offline and never enable SMU output or switch relays.

## Development setup

Install Python dependencies:

```powershell
python -m pip install -r requirements_runtime.txt
```

Run the offline scientific and hardware-safety regression suite before committing:

```powershell
python -m pytest -q
```

The test suite uses injected mock SMU/relay/environment devices and globally blocks VISA, serial, socket, production SMU-output, and physical relay entrypoints. It must never be used as a substitute for an operator-reviewed machine test.

Enable the repository-managed Git pre-push hook once after every fresh clone:

```powershell
python tools/install_git_hooks.py
```

Every subsequent `git push` creates and validates a ZIP snapshot of the exact Git commit being pushed before the remote can change. Archives are stored locally under ignored `BACKUP/`, contain only Git-tracked source plus `BACKUP_MANIFEST.json`, and retain the latest 10 matching ReliabilityX Pro backups. A backup, integrity, or retention failure blocks the push. Create a manual committed-source snapshot with:

```powershell
python tools/create_git_backup.py
```

Start the application on a prepared Windows workstation:

```powershell
python main.py
```

Runtime-mutated, user-specific, and hardware-specific JSON files are ignored by Git. Safe schemas and defaults are documented in `config/*.example.json`; the application also has in-code safe defaults when a live file is absent. Copy an example to its corresponding live filename only when local customization is needed. Never commit Telegram tokens, chat IDs, passwords, personal paths, experimental data, or calibration records.

## Documentation

- [Development and runtime guide](docs/README.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Codebase map](docs/CODEBASE_MAP.md)
- [Open items](docs/OPEN_ITEMS.md)
- [ADR index](docs/ADR_INDEX.md)
- [Version history](docs/version_history.txt)
- [AI development rules](AI_INSTRUCTIONS.md)

The repository does not redistribute third-party manuals, vendor datasheets, or research papers. Optional local reference material is kept outside version control and may be organized under `_local_only/` on developer workstations. No open-source license has been declared; public visibility alone does not grant reuse rights.
