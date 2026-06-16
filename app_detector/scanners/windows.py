"""Windows scanner & installer: registry, winget, Chocolatey.

Everything surfaced by these sources is already user-facing software (the registry
Uninstall keys, winget and choco list installed *applications*, not libraries), so
entries are marked ``manual=True`` and classified APP, except recognisable dev
tools which become TOOL. Installed size comes from the registry ``EstimatedSize``.
"""

from __future__ import annotations

import subprocess

from app_detector.models import AppEntry, Kind
from app_detector.platform_detect import _has
from app_detector.scanners.base import Installer, Scanner
from app_detector.scanners.system_packages import (
    WINDOWS_BUILTIN_EXACT, WINDOWS_BUILTIN_PREFIXES,
)

def _is_windows_system_app(name: str) -> bool:
    n = name.lower()
    return n in WINDOWS_BUILTIN_EXACT or any(n.startswith(p) for p in WINDOWS_BUILTIN_PREFIXES)


_DEV_KEYWORDS = {"python", "git", "node", "docker", "sdk", "compiler", "cmake",
                 "golang", "rust", "jdk", "maven", "gradle", "llvm", "clang",
                 "powershell", "terminal", "cli", "command line"}


def classify_windows(name: str) -> Kind:
    n = name.lower()
    if any(k in n for k in _DEV_KEYWORDS):
        return Kind.TOOL
    return Kind.APP


def _scan_registry() -> list[AppEntry]:
    ps_cmd = (
        "Get-ItemProperty "
        "HKLM:\\Software\\Wow6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*, "
        "HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*, "
        "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\* "
        "| Where-Object { $_.DisplayName -and -not $_.SystemComponent } "
        "| Select-Object DisplayName, DisplayVersion, Publisher, EstimatedSize "
        "| ConvertTo-Json -Compress"
    )
    res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd],
                         capture_output=True, text=True)
    if res.returncode != 0 or not res.stdout.strip():
        return []
    import json
    try:
        data = json.loads(res.stdout)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        data = [data]
    seen: dict[str, AppEntry] = {}
    for item in data:
        name = (item.get("DisplayName") or "").strip()
        if not name or name in seen or _is_windows_system_app(name):
            continue
        est = item.get("EstimatedSize") or 0
        try:
            size_bytes = int(est) * 1024  # registry EstimatedSize is KiB
        except (ValueError, TypeError):
            size_bytes = 0
        seen[name] = AppEntry(
            name=name, package_id=name,
            version=(item.get("DisplayVersion") or "").strip(),
            source="registry", size_bytes=size_bytes,
            kind=classify_windows(name), manual=True,
            metadata={"publisher": (item.get("Publisher") or "").strip()},
        )
    return list(seen.values())


def _scan_winget() -> list[AppEntry]:
    if not _has("winget"):
        return []
    res = subprocess.run(["winget", "list"], capture_output=True, text=True)
    if res.returncode != 0:
        return []
    entries, parsing = [], False
    for line in res.stdout.splitlines():
        if line.startswith("----"):
            parsing = True
            continue
        if not parsing or not line.strip():
            continue
        parts = [p.strip() for p in line.split("  ") if p.strip()]
        if len(parts) >= 3:
            name, pkg_id, ver = parts[0], parts[1], parts[2]
            if _is_windows_system_app(name):
                continue
            entries.append(AppEntry(
                name=name, package_id=pkg_id, version=ver, source="winget",
                kind=classify_windows(name), manual=True))
    return entries


def _scan_choco() -> list[AppEntry]:
    if not _has("choco"):
        return []
    res = subprocess.run(["choco", "list", "--local-only"],
                         capture_output=True, text=True)
    if res.returncode != 0:
        return []
    entries = []
    for line in res.stdout.splitlines():
        if "Chocolatey v" in line or "packages installed" in line:
            continue
        parts = line.split(" ", 1)
        if len(parts) == 2:
            name, ver = parts[0], parts[1]
            entries.append(AppEntry(
                name=name, package_id=name, version=ver, source="choco",
                kind=classify_windows(name), manual=True))
    return entries


class WindowsScanner(Scanner):
    def name(self) -> str:
        return "windows"

    def scan_all(self) -> list[AppEntry]:
        reg = _scan_registry()
        winget = _scan_winget()
        # Upgrade registry entries to winget IDs where names match (better install).
        winget_by_name = {a.name.lower(): a for a in winget}
        merged: dict[str, AppEntry] = {}
        for a in reg:
            match = winget_by_name.get(a.name.lower())
            if match:
                a.package_id, a.source = match.package_id, "winget"
            merged[a.name.lower()] = a
        for a in _scan_choco():
            merged.setdefault(a.name.lower(), a)
        return list(merged.values())


class WindowsInstaller(Installer):
    def install_command(self, app: AppEntry) -> list[str]:
        src, pkg = app.source, app.package_id
        ver = app.version if app.target_version == "same" else None
        if src in ("winget", "registry"):
            if src == "registry" and not _has("winget"):
                return ["echo", "No silent installer for registry-only app"]
            cmd = ["winget", "install", "--id", pkg, "--silent",
                   "--accept-package-agreements", "--accept-source-agreements"]
            if ver:
                cmd += ["--version", ver]
            return cmd
        if src == "choco":
            cmd = ["choco", "install", pkg, "-y", "--no-progress"]
            if ver:
                cmd += ["--version", ver]
            return cmd
        return ["echo", f"No silent installer for source '{src}'"]

    def install(self, app: AppEntry, silent: bool = True) -> bool:
        return self._run_install(app, self.install_command(app), silent)

    def is_installed(self, app: AppEntry) -> bool | None:
        src, pkg = app.source, app.package_id
        if src in ("winget", "registry") and _has("winget"):
            res = subprocess.run(["winget", "list", "--id", pkg],
                                 capture_output=True, text=True)
            return res.returncode == 0 and pkg.lower() in res.stdout.lower()
        if src == "choco" and _has("choco"):
            res = subprocess.run(["choco", "list", "--local-only", pkg],
                                 capture_output=True, text=True)
            return res.returncode == 0 and pkg.lower() in res.stdout.lower()
        return None
