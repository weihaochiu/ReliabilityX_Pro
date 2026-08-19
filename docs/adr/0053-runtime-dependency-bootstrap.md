# ADR 0053: Runtime Dependency Bootstrap Before Qt Startup

## Status
Accepted

## Context

When ReliabilityX Pro is copied to a new Windows computer, users often install
Python but have not yet installed PyQt6, pyvisa, pyserial, pyqtgraph, numpy,
scipy, matplotlib, reportlab, or pandas.  If `main.py` is double-clicked in that
state, Python exits immediately after the first missing import and the user only
sees a brief flashing window.

This failure mode is especially disruptive during machine bring-up because the
actual problem is an environment-preparation issue rather than a hardware or
application bug.

## Decision

Add a standard-library-only `dependency_bootstrap.py` module and call
`ensure_runtime_dependencies()` as the first executable step in `main.py`, before
importing PyQt6 or instrument drivers.

The bootstrap will:

1. Check all runtime import modules required by ReliabilityX Pro.
2. If any are missing or unusable, invoke `sys.executable -m pip install --upgrade`
   for the corresponding package names.
3. Log all actions to `logs/dependency_bootstrap.log`.
4. Show a Tk-based error dialog if installation fails before Qt is available.
5. Skip itself when running as a PyInstaller-frozen executable, where dependencies
   should already be bundled.
6. Allow maintainers to disable auto-install with `RXPRO_SKIP_AUTO_INSTALL=1`.

## Consequences

- A newly prepared Windows PC can usually start ReliabilityX Pro by running
  `main.py` or `執行.bat` without manual pip commands.
- Startup may take several minutes the first time because large wheels such as
  PyQt6, scipy, pandas, or matplotlib may need to be downloaded.
- The machine still needs non-Python drivers where applicable, especially NI-VISA
  or vendor USB/serial drivers for SMU/relay/chamber hardware.
- Production/offline deployments should still use a locked environment or a
  prebuilt EXE; the bootstrap is a safety net for source-code bring-up, not a
  substitute for release engineering.

## Files

- `dependency_bootstrap.py`
- `requirements_runtime.txt`
- `main.py`
- `執行.bat`
