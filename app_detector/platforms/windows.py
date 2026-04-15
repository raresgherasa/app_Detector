import subprocess
from app_detector.core.detector import AppDetector
from app_detector.core.installer import AppInstaller
from app_detector.models.app_entry import AppEntry
from app_detector.models.scan_level import ScanLevel
from app_detector.utils.platform_detect import _has
from app_detector.utils import logging as log

# ── Categories by Level ──────────────────────────────────────────────────────

DEV_KEYWORDS = {"python", "git", "node", "docker", "visual studio", "sdk", "compiler", "cmake", "golang", "rust", "jdk", "maven", "gradle"}

def _is_allowed(name: str, level: ScanLevel) -> bool:
    if level == ScanLevel.COMPREHENSIVE:
        return True
    
    name_lower = name.lower()
    is_dev = any(k in name_lower for k in DEV_KEYWORDS)
    
    if level == ScanLevel.ESSENTIAL and is_dev:
        return False
        
    return True

# ── Individual Scanners ──────────────────────────────────────────────────────

def _scan_registry(level: ScanLevel = ScanLevel.COMPREHENSIVE) -> list[AppEntry]:
    """Scan Windows Registry for installed software."""
    ps_cmd = (
        "Get-ItemProperty HKLM:\\Software\\Wow6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*, "
        "HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*, "
        "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\* "
        "| Select-Object DisplayName, DisplayVersion, Publisher "
        "| Where-Object { $_.DisplayName -ne $null } "
        "| Format-Table -HideTableHeaders"
    )
    res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True)
    if res.returncode != 0:
        return []

    apps: dict[str, AppEntry] = {}
    for line in res.stdout.splitlines():
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split("\t")]
        if len(parts) <= 1:
            parts = [p.strip() for p in line.split("  ")]
        if not parts:
            continue
        
        name = parts[0]
        ver = parts[1] if len(parts) > 1 else ""
        pub = parts[2] if len(parts) > 2 else ""

        if not _is_allowed(name, level):
            continue

        if name not in apps:
            apps[name] = AppEntry(
                name=name,
                package_id=name,
                version=ver,
                source="registry",
                metadata={"publisher": pub} if pub else {}
            )
            
    return list(apps.values())


def _scan_winget(level: ScanLevel = ScanLevel.COMPREHENSIVE) -> list[AppEntry]:
    """Scan using winget list."""
    if not _has("winget"):
        return []

    res = subprocess.run(["winget", "list"], capture_output=True, text=True)
    if res.returncode != 0:
        return []

    apps = []
    lines = res.stdout.splitlines()
    start_parsing = False
    
    for line in lines:
        if line.startswith("----"):
            start_parsing = True
            continue
        if not start_parsing or not line.strip():
            continue

        parts = [p.strip() for p in line.split("  ") if p.strip()]
        if len(parts) >= 3:
            name = parts[0]
            pkg_id = parts[1]
            ver = parts[2]
            
            if not _is_allowed(name, level):
                continue
                
            apps.append(AppEntry(
                name=name,
                package_id=pkg_id,
                version=ver,
                source="winget"
            ))
            
    return apps


def _scan_choco(level: ScanLevel = ScanLevel.COMPREHENSIVE) -> list[AppEntry]:
    """Scan using Chocolatey."""
    if not _has("choco"):
        return []

    res = subprocess.run(["choco", "list", "--local-only"], capture_output=True, text=True)
    if res.returncode != 0:
        return []

    apps = []
    for line in res.stdout.splitlines():
        if "Chocolatey v" in line or "packages installed" in line:
            continue
        parts = line.split(" ", 1)
        if len(parts) == 2:
            name = parts[0]
            ver = parts[1]
            
            if not _is_allowed(name, level):
                continue
                
            apps.append(AppEntry(
                name=name,
                package_id=name,
                version=ver,
                source="choco"
            ))
            
    return apps


def _map_registry_to_winget(reg_apps: list[AppEntry], winget_apps: list[AppEntry]) -> list[AppEntry]:
    """Map registry entries to winget IDs based on exact or partial display name matching."""
    winget_map = {a.name.lower(): a for a in winget_apps}
    
    final_apps = []
    for reg_app in reg_apps:
        lname = reg_app.name.lower()
        if lname in winget_map:
            # Upgrade to winget source with proper package ID
            match = winget_map[lname]
            reg_app.package_id = match.package_id
            reg_app.source = "winget"
        final_apps.append(reg_app)
        
    return final_apps


# ── Unified Windows Detector ─────────────────────────────────────────────────

class WindowsDetector(AppDetector):
    def name(self) -> str:
        return "windows"

    def scan(self, level: ScanLevel = ScanLevel.COMPREHENSIVE) -> list[AppEntry]:
        log.info("Scanning Windows [bold]Registry[/bold] …")
        reg_apps = _scan_registry(level)
        log.success(f"Registry: {len(reg_apps)} packages detected")

        winget_apps = []
        if _has("winget"):
            log.info("Scanning [bold]winget[/bold] packages …")
            winget_apps = _scan_winget(level)
            log.success(f"winget: {len(winget_apps)} packages detected")

        mapped_apps = _map_registry_to_winget(reg_apps, winget_apps)

        choco_apps = []
        if _has("choco"):
            log.info("Scanning [bold]Chocolatey[/bold] packages …")
            choco_apps = _scan_choco(level)
            log.success(f"choco: {len(choco_apps)} packages detected")

        # Combine mapped apps and choco apps (ensuring no dupes if choco and registry overlap)
        final_dict = {a.name.lower(): a for a in mapped_apps}
        for ca in choco_apps:
            if ca.name.lower() not in final_dict:
                final_dict[ca.name.lower()] = ca

        return list(final_dict.values())

# ─── Windows Installer ─────────────────────────────────────────────────────

class WindowsInstaller(AppInstaller):
    """Installs applications via the appropriate Windows package manager."""
    
    def manager_name(self) -> str:
        return "windows"
        
    def is_available(self) -> bool:
        return True
        
    def install_command(self, app: AppEntry) -> list[str]:
        src = app.source
        pkg = app.package_id
        ver = app.version if app.target_version == "same" else None
        
        if src == "winget":
            cmd = ["winget", "install", "--id", pkg, "--silent", "--accept-package-agreements", "--accept-source-agreements"]
            if ver:
                cmd.extend(["--version", ver])
            return cmd
            
        if src == "choco":
            cmd = ["choco", "install", pkg, "-y", "--no-progress"]
            if ver:
                cmd.extend(["--version", ver])
            return cmd
            
        if src == "registry":
            if not _has("winget"):
                return ["echo", f"No silent automated installer for source '{src}'"]
            cmd = ["winget", "install", "--id", pkg, "--silent", "--accept-package-agreements", "--accept-source-agreements"]
            if ver:
                cmd.extend(["--version", ver])
            return cmd
            
        return ["echo", f"No silent automated installer for source '{src}'"]
        
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
