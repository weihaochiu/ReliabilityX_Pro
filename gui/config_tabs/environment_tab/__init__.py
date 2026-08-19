"""gui/config_tabs/environment_tab package export.

Stage 2.6.1 stable package solution:
- Export EnvironmentTab from environment_tab_main.py
- Avoid the module/package naming collision that happened when
  `environment_tab.py` existed both as a file and as a package name.
"""

from .environment_tab_main import EnvironmentTab

__all__ = ["EnvironmentTab"]
