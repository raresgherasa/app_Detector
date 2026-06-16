"""Where App Detector keeps its own user-level state (overrides, etc.).

Honours ``$XDG_CONFIG_HOME`` on Linux/macOS and ``%APPDATA%`` on Windows, falling
back to ``~/.config``. The directory is created on demand.
"""

from __future__ import annotations

import os
from pathlib import Path

_APP_DIR = "app_detector"


def config_dir() -> Path:
    """Return (and create) the per-user config directory for App Detector."""
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    d = Path(base) / _APP_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_file(name: str) -> Path:
    """Path to a named file inside the config dir (not necessarily existing)."""
    return config_dir() / name
