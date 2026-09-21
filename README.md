# ReliabilityX Pro

GSM compatibility follow-up (OI-057): source readbacks now use the manual-listed
CURR?/VOLT? queries. Diagnostic failures explain the stopped stage, likely causes,
next actions and confirmed/unknown cleanup, with expandable/copyable technical
evidence. Relay controller state is not a physical continuity test; see the updated
[量測流程與故障說明](docs/MEASUREMENT_FLOW.md). No dependency/build changes.

2026-09-21 safety update: qualified measured-V/I R-line calibration, verified Relay
state masks, and mandatory illuminated-solar-cell polarity before every formal
sweep. Legacy R-line records are preserved but require remeasurement. Raw IV uses
measured voltage; per-point compliance failures abort rather than produce a normal
curve. See [量測流程與上機驗收](docs/MEASUREMENT_FLOW.md). No new dependencies or
build flags; physical hardware acceptance remains operator-controlled (OI-056).

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

## Hardware connection diagnostics

Hardware startup logs provide stage-specific evidence instead of only reporting a generic connection failure. SMU logs include the VISA backend/resources, target resource, timeout, `*IDN?` response, failure stage, traceback, and cleanup attempt. Relay logs include the Windows/pyserial COM inventory and each `ver\r` TX/RX probe, distinguishing no ports, open errors, timeout, and identifier mismatch. Chamber logs include COM inventory/open classification and per-FCS telemetry TX/RX, timeout, validation, and traceback details.

The System Configuration SMU page reloads the saved interface, IP/VISA address, and NPLC without clearing the restored address. If the persisted address is missing while an SMU is already connected, the active connection setting is shown as a fallback.

## Documentation

- [Development and runtime guide](docs/README.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Codebase map](docs/CODEBASE_MAP.md)
- [Open items](docs/OPEN_ITEMS.md)
- [ADR index](docs/ADR_INDEX.md)
- [Version history](docs/version_history.txt)
- [AI development rules](AI_INSTRUCTIONS.md)

The repository does not redistribute third-party manuals, vendor datasheets, or research papers. Optional local reference material is kept outside version control and may be organized under `_local_only/` on developer workstations. No open-source license has been declared; public visibility alone does not grant reuse rights.

## Multi-channel machine-test update (2026-09-20)

OI-050/051 are fixed. Start selected channels once; positive per-channel intervals repeat automatically on the shared SMU. Individual checkboxes now pause/resume at safe channel boundaries after settings save. All-paused sessions keep waiting. A failed attempt stops the global scheduler and is never counted as successful. Cards use canonical forward Corr/Raw values and show invalid data explicitly.

On a Windows test station, run `setup_and_check.bat` to create a Python 3.11 venv (if absent), install `requirements_test.txt`, and run mock-only tests. Then launch `執行.bat` separately. See [machine-test instructions](docs/MACHINE_TEST_GUIDE.md). App startup does not automatically begin a measurement. Physical-machine validation remains required.
