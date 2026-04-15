"""Abstract base classes for platform scanners."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app_detector.models.app_entry import AppEntry
from app_detector.models.scan_level import ScanLevel


class AppDetector(ABC):
    """Scans the current OS for installed applications."""

    @abstractmethod
    def scan(self, level: ScanLevel = ScanLevel.COMPREHENSIVE) -> list[AppEntry]:
        """Return a list of every detected application."""
        ...

    @abstractmethod
    def name(self) -> str:
        """Human-readable scanner name (e.g. 'apt', 'winget')."""
        ...
