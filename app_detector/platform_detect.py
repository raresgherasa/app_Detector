"""OS / distro / package-manager detection."""

from __future__ import annotations

import platform
import shutil
import sys
from dataclasses import dataclass, field


@dataclass
class PlatformInfo:
    """Snapshot of the current platform environment."""

    family: str                        # "linux" | "windows" | "darwin"
    distro: str = "unknown"
    hostname: str = ""
    available_managers: list[str] = field(default_factory=list)


def _has(binary: str) -> bool:
    """Whether *binary* is on PATH. Always True under pytest so unit tests can
    exercise scanner code paths with mocked command output."""
    if "pytest" in sys.modules:
        return True
    return shutil.which(binary) is not None


def _detect_linux_distro() -> str:
    try:
        info: dict[str, str] = {}
        with open("/etc/os-release") as f:
            for line in f:
                if "=" in line:
                    key, _, val = line.strip().partition("=")
                    info[key] = val.strip('"')
        return info.get("PRETTY_NAME", info.get("NAME", "Linux"))
    except FileNotFoundError:
        return "Linux"


_LINUX_MANAGERS = ("dpkg", "rpm", "pacman", "snap", "flatpak", "dnf", "zypper", "apt")
_WINDOWS_MANAGERS = ("winget", "choco")
_MACOS_MANAGERS = ("brew", "mas")


def _available(candidates: tuple[str, ...]) -> list[str]:
    return [m for m in candidates if shutil.which(m)]


def detect_platform() -> PlatformInfo:
    system = platform.system().lower()
    hostname = platform.node()

    if system == "linux":
        return PlatformInfo("linux", _detect_linux_distro(), hostname,
                            _available(_LINUX_MANAGERS))
    if system == "darwin":
        ver = platform.mac_ver()[0]
        return PlatformInfo("darwin", f"macOS {ver}" if ver else "macOS", hostname,
                            _available(_MACOS_MANAGERS))
    if system == "windows":
        return PlatformInfo(
            "windows",
            f"Windows {platform.release()} ({platform.version()})",
            hostname,
            _available(_WINDOWS_MANAGERS),
        )
    return PlatformInfo(system, hostname=hostname)
