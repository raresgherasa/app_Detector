"""Platform factory: pick the right Scanner / Installer for this OS."""

from __future__ import annotations

import sys

from app_detector.platform_detect import detect_platform
from app_detector.scanners.base import Installer, Scanner
from app_detector.util import log


def get_scanner() -> Scanner:
    fam = detect_platform().family
    if fam == "linux":
        from app_detector.scanners.linux import LinuxScanner
        return LinuxScanner()
    if fam == "windows":
        from app_detector.scanners.windows import WindowsScanner
        return WindowsScanner()
    if fam == "darwin":
        from app_detector.scanners.macos import MacOSScanner
        return MacOSScanner()
    log.error(f"Unsupported platform: {fam}")
    sys.exit(1)


def get_installer() -> Installer:
    fam = detect_platform().family
    if fam == "linux":
        from app_detector.scanners.linux import LinuxInstaller
        return LinuxInstaller()
    if fam == "windows":
        from app_detector.scanners.windows import WindowsInstaller
        return WindowsInstaller()
    if fam == "darwin":
        from app_detector.scanners.macos import MacOSInstaller
        return MacOSInstaller()
    log.error(f"Unsupported platform: {fam}")
    sys.exit(1)
