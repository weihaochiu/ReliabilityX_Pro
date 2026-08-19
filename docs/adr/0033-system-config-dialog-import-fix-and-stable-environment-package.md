# ADR 0033: System Config Dialog Import Fix and Stable Environment Package

## Status
Accepted

## Context
The system still imported:
`from .config_tabs.environment.environment_tab import EnvironmentTab`

But the refactor moved environment tabs away from that path. In addition, the
previous attempt created a risky file/package name collision with both:
- `gui/config_tabs/environment_tab.py`
- `gui/config_tabs/environment_tab/`

## Decision
1. Use the stable package approach.
2. Place the parent EnvironmentTab class in:
   `gui/config_tabs/environment_tab/environment_tab_main.py`
3. Export it from:
   `gui/config_tabs/environment_tab/__init__.py`
4. Update `system_config_dialog.py` to import:
   `from .config_tabs.environment_tab import EnvironmentTab`
5. Merge current and older dialog logic so logging helpers are not lost.

## Consequences
- Fixes the immediate import error
- Avoids module/package naming conflict
- Preserves more of the original system-config functionality
