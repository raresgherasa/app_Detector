"""Linux application scanner and installer.

Supports: dpkg/apt, rpm/dnf, pacman, snap, flatpak.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import Callable

from app_detector.core.detector import AppDetector
from app_detector.core.installer import AppInstaller
from app_detector.models.app_entry import AppEntry
from app_detector.models.scan_level import ScanLevel
from app_detector.utils.platform_detect import _has
from app_detector.utils import logging as log


# ─── Helpers ────────────────────────────────────────────────────────────────

def _run(cmd: list[str], timeout: int = 30) -> str | None:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


# ── Categories by Level ──────────────────────────────────────────────────────

ESSENTIAL_SECTIONS = {"gnome", "kde", "x11", "graphics", "sound", "video", "web", "games", "math", "text"}
DEVELOPMENT_SECTIONS = {"devel", "vcs", "editors", "database", "python", "java", "rust", "golang", "ruby", "perl", "shells", "httpd"}


def _is_allowed(name: str, section: str, level: ScanLevel, source: str) -> bool:
    """Determine if a package should be included given the current scan level."""
    if level == ScanLevel.COMPREHENSIVE:
        return True
    
    # Snap and Flatpak are almost exclusively GUI / Essential tools
    if source in ("snap", "flatpak"):
        return True

    sec = section.lower()
    
    # Essential Level
    if level == ScanLevel.ESSENTIAL:
        return any(s in sec for s in ESSENTIAL_SECTIONS)
    
    # Development Level
    if level == ScanLevel.DEVELOPMENT:
        return any(s in sec for s in ESSENTIAL_SECTIONS) or any(s in sec for s in DEVELOPMENT_SECTIONS)
        
    return True


# ─── Individual Scanners ────────────────────────────────────────────────────

def _scan_dpkg(level: ScanLevel = ScanLevel.COMPREHENSIVE) -> list[AppEntry]:
    """Scan Debian-based systems using dpkg-query."""
    if not _has("dpkg-query"):
        return []
    
    # Notice we added ${Section} to the output format
    fmt = r"${Package}\t${Version}\t${binary:Summary}\n"
    try:
        res = subprocess.run(["dpkg-query", "-W", f"-f={fmt}"], capture_output=True, text=True, timeout=10)
        if res.returncode != 0:
            return []
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
        
    apps = []
    for line in res.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3:
            name = parts[0]
            ver = parts[1]
            sec = parts[2]
            desc = parts[2]
            
            if not _is_allowed(name, sec, level, "apt"):
                continue
                
            apps.append(
                AppEntry(
                    name=name,
                    package_id=name,
                    version=ver,
                    source="apt",
                    metadata={"description": desc, "section": sec}
                )
            )
    return apps


def _scan_rpm(level: ScanLevel = ScanLevel.COMPREHENSIVE) -> list[AppEntry]:
    """Scan RedHat-based systems using rpm."""
    if not _has("rpm"):
        return []
        
    fmt = "%{NAME}\t%{VERSION}\t%{GROUP}\t%{SUMMARY}\n"
    res = subprocess.run(["rpm", "-qa", "--queryformat", fmt], capture_output=True, text=True)
    if res.returncode != 0:
        return []
        
    apps = []
    for line in res.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3:
            name = parts[0]
            ver = parts[1]
            group = parts[2]
            desc = parts[3] if len(parts) > 3 else ""
            
            if not _is_allowed(name, group, level, "dnf"):
                continue

            apps.append(
                AppEntry(
                    name=name,
                    package_id=name,
                    version=ver,
                    source="dnf",
                    metadata={"description": desc, "group": group}
                )
            )
    return apps


def _scan_pacman(level: ScanLevel = ScanLevel.COMPREHENSIVE) -> list[AppEntry]:
    """Scan packages installed via pacman (Arch family)."""
    out = _run(["pacman", "-Q"])
    if not out:
        return []

    apps: list[AppEntry] = []
    for line in out.splitlines():
        parts = line.split(None, 1)
        if len(parts) < 2:
            continue
        apps.append(AppEntry(
            name=parts[0],
            package_id=parts[0],
            version=parts[1],
            source="pacman",
        ))
    return apps


def _scan_snap(level: ScanLevel = ScanLevel.COMPREHENSIVE) -> list[AppEntry]:
    """Scan packages installed via snap."""
    out = _run(["snap", "list"])
    if not out:
        return []

    apps: list[AppEntry] = []
    lines = out.splitlines()
    if len(lines) < 2:
        return []

    for line in lines[1:]:  # skip header
        cols = line.split()
        if len(cols) < 2:
            continue
        name, ver = cols[0], cols[1]
        channel = cols[4] if len(cols) > 4 else ""
        apps.append(AppEntry(
            name=name,
            package_id=name,
            version=ver,
            source="snap",
            metadata={"channel": channel} if channel else {},
        ))
    return apps


def _scan_flatpak(level: ScanLevel = ScanLevel.COMPREHENSIVE) -> list[AppEntry]:
    """Scan packages installed via flatpak."""
    out = _run([
        "flatpak", "list", "--app",
        "--columns=application,version,name",
    ])
    if not out:
        return []

    apps: list[AppEntry] = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        app_id = parts[0].strip()
        ver = parts[1].strip() if len(parts) > 1 else ""
        display = parts[2].strip() if len(parts) > 2 else app_id
        apps.append(AppEntry(
            name=display,
            package_id=app_id,
            version=ver,
            source="flatpak",
        ))
    return apps


# ─── Unified Linux Detector ────────────────────────────────────────────────

class LinuxDetector(AppDetector):
    """Aggregate scanner that probes every available Linux package manager."""

    SCANNERS: list[tuple[str, Callable[[ScanLevel], list[AppEntry]]]] = [
        ("dpkg",    _scan_dpkg),
        ("rpm",     _scan_rpm),
        ("pacman",  _scan_pacman),
        ("snap",    _scan_snap),
        ("flatpak", _scan_flatpak),
    ]

    def name(self) -> str:
        return "linux"

    def scan(self, level: ScanLevel = ScanLevel.COMPREHENSIVE) -> list[AppEntry]:
        all_apps: list[AppEntry] = []
        for mgr_binary, scanner_fn in self.SCANNERS:
            if not _has(mgr_binary):
                continue
            log.info(f"Scanning [bold]{mgr_binary}[/bold] packages …")
            found = scanner_fn(level)
            log.success(f"{mgr_binary}: {len(found)} packages detected")
            all_apps.extend(found)
        return all_apps


# ─── Linux Installer ───────────────────────────────────────────────────────

class LinuxInstaller(AppInstaller):
    """Installs applications via the appropriate Linux package manager."""

    def manager_name(self) -> str:
        return "linux"

    def is_available(self) -> bool:
        return True  # at least one manager will exist

    def install_command(self, app: AppEntry) -> list[str]:
        src = app.source
        pkg = app.package_id
        ver = app.version if app.target_version == "same" else None

        if src == "apt":
            if ver:
                return ["sudo", "apt", "install", "-y", f"{pkg}={ver}"]
            return ["sudo", "apt", "install", "-y", pkg]

        if src in ("dnf", "rpm"):
            if ver:
                return ["sudo", "dnf", "install", "-y", f"{pkg}-{ver}"]
            return ["sudo", "dnf", "install", "-y", pkg]

        if src == "pacman":
            return ["sudo", "pacman", "-S", "--noconfirm", pkg]

        if src == "snap":
            cmd = ["sudo", "snap", "install", pkg]
            channel = app.metadata.get("channel")
            if channel:
                cmd.extend(["--channel", channel])
            return cmd

        if src == "flatpak":
            return ["flatpak", "install", "-y", pkg]

        return ["echo", f"No installer for source '{src}'"]

    def install(self, app: AppEntry, silent: bool = True) -> bool:
        cmd = self.install_command(app)
        log.info(f"Running: {' '.join(cmd)}")
        try:
            r = subprocess.run(
                cmd,
                capture_output=silent,
                text=True,
                timeout=300,
            )
            return r.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            log.error(f"Install failed for {app.name}: {exc}")
            return False
