"""Abstract base class for platform installers."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app_detector.models.app_entry import AppEntry


class AppInstaller(ABC):
    """Installs applications on the current OS."""

    @abstractmethod
    def install(self, app: AppEntry, silent: bool = True) -> bool:
        """Install *app* and return ``True`` on success."""
        ...

    @abstractmethod
    def install_command(self, app: AppEntry) -> list[str]:
        """Return the CLI command that would install *app* (for dry-run)."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Return ``True`` if this installer's package manager is present."""
        ...

    @abstractmethod
    def manager_name(self) -> str:
        """Human-readable name of the package manager."""
        ...
