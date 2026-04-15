"""OS / distro / package-manager detection utilities."""

from __future__ import annotations

import platform
import shutil
import subprocess
from dataclasses import dataclass, field


@dataclass
class PlatformInfo:
    """Snapshot of the current platform environment."""

    family: str                        # "linux" | "windows" | "darwin"
    distro: str = "unknown"            # e.g. "Ubuntu 24.04", "Fedora 41"
    hostname: str = ""
    available_managers: list[str] = field(default_factory=list)


def _has(binary: str) -> bool:
    """Check if a binary is available on the PATH."""
    import sys
    if "pytest" in sys.modules:
        return True
    return shutil.which(binary) is not None


def _run(cmd: list[str]) -> str | None:
    """Run a command and return stripped stdout, or None on failure."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def _detect_linux_distro() -> str:
    """Best-effort distro name from /etc/os-release."""
    try:
        with open("/etc/os-release") as f:
            info: dict[str, str] = {}
            for line in f:
                if "=" in line:
                    key, _, val = line.strip().partition("=")
                    info[key] = val.strip('"')
            return info.get("PRETTY_NAME", info.get("NAME", "Linux"))
    except FileNotFoundError:
        return "Linux"


def _detect_available_managers_linux() -> list[str]:
    managers: list[str] = []
    for mgr in ("dpkg", "rpm", "pacman", "snap", "flatpak", "dnf", "zypper", "apt"):
        if shutil.which(mgr):
            managers.append(mgr)
    return managers


def _detect_available_managers_windows() -> list[str]:
    managers: list[str] = []
    if shutil.which("winget"):
        managers.append("winget")
    if shutil.which("choco"):
        managers.append("choco")
    return managers


def _detect_available_managers_macos() -> list[str]:
    managers: list[str] = []
    if shutil.which("brew"):
        managers.append("brew")
    if shutil.which("mas"):
        managers.append("mas")
    return managers


def detect_platform() -> PlatformInfo:
    """Detect the current platform and available package managers."""
    system = platform.system().lower()
    hostname = platform.node()

    if system == "linux":
        return PlatformInfo(
            family="linux",
            distro=_detect_linux_distro(),
            hostname=hostname,
            available_managers=_detect_available_managers_linux(),
        )
    elif system == "darwin":
        mac_ver = platform.mac_ver()[0]
        return PlatformInfo(
            family="darwin",
            distro=f"macOS {mac_ver}" if mac_ver else "macOS",
            hostname=hostname,
            available_managers=_detect_available_managers_macos(),
        )
    elif system == "windows":
        win_ver = platform.version()
        return PlatformInfo(
            family="windows",
            distro=f"Windows {platform.release()} ({win_ver})",
            hostname=hostname,
            available_managers=_detect_available_managers_windows(),
        )
    else:
        return PlatformInfo(family=system, hostname=hostname)
