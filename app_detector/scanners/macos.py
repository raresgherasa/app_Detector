"""macOS scanner & installer: system_profiler, Homebrew, /Applications.

GUI apps come from ``system_profiler`` / brew casks (Kind.APP); brew formulae are
CLI tools. ``brew leaves`` (formulae nothing depends on) marks formulae as manual;
casks and GUI apps are user-facing so manual=True. Size comes from ``du`` on the
``.app`` bundle path.
"""

from __future__ import annotations

import json
import os
import subprocess

from app_detector.models import AppEntry, Kind
from app_detector.platform_detect import _has
from app_detector.scanners.base import Installer, Scanner, run
from app_detector.scanners.system_packages import MACOS_SYSTEM_APPS


def _du_bytes(path: str | None) -> int:
    if not path or not os.path.isdir(path):
        return 0
    out = run(["du", "-sk", path])
    if not out:
        return 0
    try:
        return int(out.split()[0]) * 1024
    except (ValueError, IndexError):
        return 0


def _scan_system_profiler() -> list[AppEntry]:
    res = subprocess.run(["system_profiler", "SPApplicationsDataType", "-json"],
                         capture_output=True, text=True)
    if res.returncode != 0:
        return []
    try:
        data = json.loads(res.stdout)
    except json.JSONDecodeError:
        return []
    entries = []
    for item in data.get("SPApplicationsDataType", []):
        name = item.get("_name")
        if not name:
            continue
        path = item.get("path", "")
        if path and path.startswith("/System/"):
            continue
        if name.lower() in MACOS_SYSTEM_APPS:
            continue
        entries.append(AppEntry(
            name=name, package_id=name, version=item.get("version", ""),
            source="system", size_bytes=_du_bytes(path),
            kind=Kind.APP, manual=True,
            metadata={"path": path} if path else {}))
    return entries


def _brew_leaves() -> set[str]:
    out = run(["brew", "leaves"])
    return set(out.splitlines()) if out else set()


def _scan_brew_formulae(leaves: set[str]) -> list[AppEntry]:
    if not _has("brew"):
        return []
    out = run(["brew", "list", "--formula", "--versions"])
    if not out:
        return []
    entries = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            name = parts[0]
            entries.append(AppEntry(
                name=name, package_id=name, version=parts[1], source="brew",
                kind=Kind.TOOL, manual=(name in leaves) if leaves else True))
    return entries


def _scan_brew_casks() -> list[AppEntry]:
    if not _has("brew"):
        return []
    out = run(["brew", "list", "--cask", "--versions"])
    if not out:
        return []
    entries = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            entries.append(AppEntry(
                name=parts[0], package_id=parts[0], version=parts[1],
                source="brew-cask", kind=Kind.APP, manual=True))
    return entries


class MacOSScanner(Scanner):
    def name(self) -> str:
        return "macos"

    def scan_all(self) -> list[AppEntry]:
        merged: dict[str, AppEntry] = {}
        for a in _scan_system_profiler():
            merged[a.name.lower()] = a
        if _has("brew"):
            leaves = _brew_leaves()
            for a in _scan_brew_formulae(leaves):
                merged[a.name.lower()] = a
            for a in _scan_brew_casks():
                merged[a.name.lower()] = a
        return list(merged.values())


class MacOSInstaller(Installer):
    def install_command(self, app: AppEntry) -> list[str]:
        src, pkg = app.source, app.package_id
        ver = app.version if app.target_version == "same" else None
        if src == "brew":
            return ["brew", "install", f"{pkg}@{ver}" if ver else pkg]
        if src in ("brew-cask", "system"):
            return ["brew", "install", "--cask", pkg]
        if src == "mas":
            return ["mas", "install", pkg] if _has("mas") else \
                   ["brew", "install", "--cask", pkg]
        return ["echo", f"No silent installer for source '{src}'"]

    def install(self, app: AppEntry, silent: bool = True) -> bool:
        return self._run_install(app, self.install_command(app), silent)

    def is_installed(self, app: AppEntry) -> bool | None:
        src, pkg = app.source, app.package_id
        if src in ("brew-cask", "system"):
            if _has("brew") and run(["brew", "list", "--cask", pkg]) is not None:
                return True
            path = app.metadata.get("path")
            return os.path.isdir(path) if path else None
        if src == "brew":
            return run(["brew", "list", pkg]) is not None if _has("brew") else None
        return None
