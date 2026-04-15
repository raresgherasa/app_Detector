import subprocess
import json
import os
from app_detector.core.detector import AppDetector
from app_detector.core.installer import AppInstaller
from app_detector.models.app_entry import AppEntry
from app_detector.models.scan_level import ScanLevel
from app_detector.utils.platform_detect import _has
from app_detector.utils import logging as log

# ── Individual Scanners ──────────────────────────────────────────────────────

def _scan_system_profiler(level: ScanLevel = ScanLevel.COMPREHENSIVE) -> list[AppEntry]:
    """Scan GUI applications using macOS system_profiler."""
    try:
        res = subprocess.run(
            ["system_profiler", "SPApplicationsDataType", "-json"],
            capture_output=True, text=True
        )
        if res.returncode != 0:
            return []
            
        data = json.loads(res.stdout)
        apps = []
        for item in data.get("SPApplicationsDataType", []):
            name = item.get("_name")
            if not name:
                continue
            apps.append(AppEntry(
                name=name,
                package_id=name,
                version=item.get("version", "unknown"),
                source="system",
                metadata={"path": item.get("path")} if item.get("path") else {}
            ))
        return apps
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _scan_brew_formulae(level: ScanLevel = ScanLevel.COMPREHENSIVE) -> list[AppEntry]:
    """Scan Homebrew CLI packages."""
    if level == ScanLevel.ESSENTIAL:
        return []  # No dev tools in essential level

    if not _has("brew"):
        return []
        
    try:
        res = subprocess.run(["brew", "list", "--formula", "--versions"], capture_output=True, text=True, timeout=10)
        if res.returncode != 0:
            return []
            
        apps = []
        for line in res.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                apps.append(AppEntry(
                    name=parts[0],
                    package_id=parts[0],
                    version=parts[1],
                    source="brew"
                ))
        return apps
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []


def _scan_brew_casks(level: ScanLevel = ScanLevel.COMPREHENSIVE) -> list[AppEntry]:
    """Scan Homebrew GUI casks."""
    if not _has("brew"):
        return []
        
    try:
        res = subprocess.run(["brew", "list", "--cask", "--versions"], capture_output=True, text=True, timeout=10)
        if res.returncode != 0:
            return []
            
        apps = []
        for line in res.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                apps.append(AppEntry(
                    name=parts[0],
                    package_id=parts[0],
                    version=parts[1],
                    source="brew-cask"
                ))
        return apps
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []


def _scan_applications_dir(level: ScanLevel = ScanLevel.COMPREHENSIVE) -> list[AppEntry]:
    """Fallback scanner for the /Applications folder."""
    if not os.path.isdir("/Applications"):
        return []
        
    apps = []
    for item in os.listdir("/Applications"):
        if item.endswith(".app"):
            name = item[:-4]
            apps.append(AppEntry(
                name=name,
                package_id=name.lower().replace(" ", "-"),
                version="unknown",
                source="applications-dir"
            ))
    return apps


# ── Unified macOS Detector ───────────────────────────────────────────────────

class MacOSDetector(AppDetector):
    def name(self) -> str:
        return "macos"

    def scan(self, level: ScanLevel = ScanLevel.COMPREHENSIVE) -> list[AppEntry]:
        all_apps: dict[str, AppEntry] = {}

        log.info("Scanning GUI Apps ([bold]system_profiler[/bold]) …")
        sp_apps = _scan_system_profiler(level)
        for app in sp_apps:
            all_apps[app.name.lower()] = app
        log.success(f"system_profiler: {len(sp_apps)} apps detected")

        if _has("brew"):
            log.info("Scanning Homebrew [bold]formulae[/bold] …")
            formulae = _scan_brew_formulae(level)
            for app in formulae:
                all_apps[app.name.lower()] = app
            log.success(f"brew formula: {len(formulae)} apps detected")

            log.info("Scanning Homebrew [bold]casks[/bold] …")
            casks = _scan_brew_casks(level)
            for app in casks:
                all_apps[app.name.lower()] = app
            log.success(f"brew cask: {len(casks)} apps detected")

        # Fallback directory scan for apps not registered
        log.info("Scanning [bold]/Applications[/bold] directory …")
        dir_apps = _scan_applications_dir(level)
        added = 0
        for app in dir_apps:
            if app.name.lower() not in all_apps:
                all_apps[app.name.lower()] = app
                added += 1
        log.success(f"/Applications: {added} additional unmanaged apps detected")

        return list(all_apps.values())

# ─── macOS Installer ───────────────────────────────────────────────────────

class MacOSInstaller(AppInstaller):
    """Installs applications via the appropriate macOS package manager."""
    
    def manager_name(self) -> str:
        return "macos"
        
    def is_available(self) -> bool:
        return True
        
    def install_command(self, app: AppEntry) -> list[str]:
        src = app.source
        pkg = app.package_id
        ver = app.version if app.target_version == "same" else None
        
        if src == "brew":
            if ver:
                return ["brew", "install", f"{pkg}@{ver}"]
            return ["brew", "install", pkg]
            
        if src == "brew-cask":
            return ["brew", "install", "--cask", pkg]
            
        if src == "mas":
            if not _has("mas"):
                return ["brew", "install", "--cask", pkg]
            return ["mas", "install", pkg]
            
        if src in ("system", "applications-dir"):
            return ["brew", "install", "--cask", pkg]
            
        return ["echo", f"No silent installer for source '{src}'"]
        
    def install(self, app: AppEntry, silent: bool = True) -> bool:
        cmd = self.install_command(app)
        if cmd[0] == "echo":
             return False
             
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
