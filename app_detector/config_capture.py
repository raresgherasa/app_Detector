"""Capture & restore the *configuration* that lives alongside installed apps.

Reinstalling Firefox is easy; re-adding your VS Code extensions and git identity
by hand is the annoying part. Each :class:`ConfigHandler` snapshots one such
slice into JSON and replays it on restore. Handlers are deliberately limited to
**safe, idempotent, list-style** state (extensions, key/value config) — never
blind file overwrites — so applying a snapshot can't clobber newer local work.

Add a handler by subclassing :class:`ConfigHandler` and appending to
:data:`HANDLERS`.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import Any, Callable

from app_detector.scanners.base import run
from app_detector.util import log


class ConfigHandler:
    id: str = ""
    label: str = ""

    def is_available(self) -> bool:
        """Is the underlying tool present on this machine?"""
        raise NotImplementedError

    def capture(self) -> Any | None:
        """Return a JSON-serialisable snapshot, or ``None`` if nothing to save."""
        raise NotImplementedError

    def restore(self, data: Any) -> bool:
        """Apply a previously-captured snapshot. Return True on success."""
        raise NotImplementedError


class VSCodeExtensions(ConfigHandler):
    id = "vscode_extensions"
    label = "VS Code extensions"

    def is_available(self) -> bool:
        return shutil.which("code") is not None

    def capture(self) -> list[str] | None:
        out = run(["code", "--list-extensions"])
        exts = [e.strip() for e in out.splitlines() if e.strip()] if out else []
        return exts or None

    def restore(self, data: Any) -> bool:
        if not isinstance(data, list):
            return False
        ok = True
        for ext in data:
            r = subprocess.run(["code", "--install-extension", ext],
                               capture_output=True, text=True)
            if r.returncode != 0:
                log.warn(f"  extension failed: {ext}")
                ok = False
        return ok


class GitConfig(ConfigHandler):
    id = "git_config"
    label = "Git global config"

    def is_available(self) -> bool:
        return shutil.which("git") is not None

    def capture(self) -> dict[str, str] | None:
        out = run(["git", "config", "--global", "--list"])
        if not out:
            return None
        data: dict[str, str] = {}
        for line in out.splitlines():
            key, _, val = line.partition("=")
            if key:
                data[key.strip()] = val.strip()
        return data or None

    def restore(self, data: Any) -> bool:
        if not isinstance(data, dict):
            return False
        ok = True
        for key, val in data.items():
            r = subprocess.run(["git", "config", "--global", key, val],
                               capture_output=True, text=True)
            if r.returncode != 0:
                ok = False
        return ok


HANDLERS: list[ConfigHandler] = [VSCodeExtensions(), GitConfig()]


def capture_all() -> dict[str, Any]:
    """Snapshot every available handler that has something to save."""
    out: dict[str, Any] = {}
    for h in HANDLERS:
        if not h.is_available():
            continue
        data = h.capture()
        if data:
            out[h.id] = data
            log.success(f"Captured {h.label}.")
    return out


def restore_all(configs: dict[str, Any],
                on_line: Callable[[str], None] | None = None) -> dict[str, bool]:
    """Replay captured configs; returns ``{handler_id: succeeded}``.

    ``on_line(text)`` — if given — receives a progress line per handler so a GUI
    console can show what's happening (the CLI relies on the rich ``log`` calls).
    """
    emit = on_line or (lambda _t: None)
    by_id = {h.id: h for h in HANDLERS}
    results: dict[str, bool] = {}
    for cid, data in configs.items():
        handler = by_id.get(cid)
        if handler is None:
            continue
        if not handler.is_available():
            log.warn(f"Skipping {handler.label}: tool not installed.")
            emit(f"  skipped {handler.label}: tool not installed.\n")
            continue
        log.info(f"Restoring {handler.label} …")
        emit(f"  restoring {handler.label} …\n")
        ok = handler.restore(data)
        results[cid] = ok
        emit(("  ✓ " if ok else "  ✗ ") + f"{handler.label}\n")
    return results
