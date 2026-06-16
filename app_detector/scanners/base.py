"""Abstract contracts for platform scanners and installers."""

from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod

from app_detector.models import AppEntry


def run(cmd: list[str], timeout: int = 30) -> str | None:
    """Run *cmd*, returning stripped stdout, or ``None`` on any failure."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else None
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None


class Scanner(ABC):
    """Scans the current OS for *every* installed package, fully enriched.

    Implementations must populate ``size_bytes``, ``kind`` and ``manual`` on each
    entry. Filtering is intentionally NOT done here — callers filter the dataset.
    """

    @abstractmethod
    def scan_all(self) -> list[AppEntry]:
        ...

    @abstractmethod
    def name(self) -> str:
        ...


class Installer(ABC):
    """Installs applications on the current OS."""

    @abstractmethod
    def install_command(self, app: AppEntry) -> list[str]:
        ...

    @abstractmethod
    def install(self, app: AppEntry, silent: bool = True) -> bool:
        ...

    def is_installed(self, app: AppEntry) -> bool | None:
        """Cheap post-install presence check.

        Returns ``True``/``False`` when the platform can verify, or ``None`` when
        it cannot determine presence (treated as "unknown", not "failed"). The
        default is ``None``; platform installers override it.
        """
        return None

    def _run_install(self, app: AppEntry, cmd: list[str], silent: bool) -> bool:
        from app_detector.util import log
        if cmd and cmd[0] == "echo":
            return False
        log.info(f"Running: {' '.join(cmd)}")
        try:
            r = subprocess.run(cmd, capture_output=silent, text=True, timeout=600)
            return r.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
            log.error(f"Install failed for {app.name}: {exc}")
            return False

    def install_streamed(self, app: AppEntry, on_line) -> bool:
        """Run the install command, forwarding each output line to ``on_line``.

        ``on_line(text)`` is invoked from the *calling* thread as output
        arrives, so a GUI caller must marshal it back to its UI thread. stdin
        is left attached to the controlling terminal so ``sudo`` can still
        prompt for a password there. Returns True on a zero exit code.
        """
        cmd = self.install_command(app)
        if cmd and cmd[0] == "echo":
            on_line(f"No installer available for source '{app.source}'.\n")
            return False
        on_line("$ " + " ".join(cmd) + "\n")
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True,
                                    bufsize=1)
        except (FileNotFoundError, OSError) as exc:
            on_line(f"Failed to start: {exc}\n")
            return False
        try:
            for line in proc.stdout:        # streams until the process exits
                on_line(line)
            proc.wait(timeout=600)
        except subprocess.TimeoutExpired:
            proc.kill()
            on_line("Timed out after 600s.\n")
            return False
        return proc.returncode == 0
