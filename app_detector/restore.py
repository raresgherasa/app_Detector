"""Restore orchestration: resolve → install → verify → report.

Keeps the "did it actually work?" logic out of the CLI/GUI so both can share it.
A restore is three honest steps:

1. **resolve** every app to something the *target* OS can install (see
   :mod:`app_detector.resolve`); apps with no installable manager are set aside.
2. **install** each resolved app.
3. **verify** it is actually present afterwards (``Installer.is_installed``),
   so a package manager that exits 0 without installing can't fake success.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from app_detector.models import AppEntry
from app_detector.platform_detect import PlatformInfo
from app_detector.resolve import resolve
from app_detector.scanners.base import Installer


@dataclass
class RestoreResult:
    """Outcome for a single app."""

    original: AppEntry           # entry as recorded in the manifest
    resolved: AppEntry           # what we actually tried to install
    confidence: str              # exact | mapped | guess
    installed: bool              # the install command exited successfully
    verified: bool | None        # is_installed() afterwards (None = couldn't check)

    @property
    def ok(self) -> bool:
        # Trust verification when we have it; otherwise fall back to the exit code.
        return self.verified if self.verified is not None else self.installed


@dataclass
class RestoreReport:
    results: list[RestoreResult] = field(default_factory=list)
    unresolved: list[AppEntry] = field(default_factory=list)  # no manager on this OS

    @property
    def ok(self) -> list[RestoreResult]:
        return [r for r in self.results if r.ok]

    @property
    def failed(self) -> list[RestoreResult]:
        return [r for r in self.results if not r.ok]


def plan(apps: list[AppEntry], info: PlatformInfo,
         ) -> tuple[list[tuple[AppEntry, AppEntry, str]], list[AppEntry]]:
    """Split *apps* into ``[(original, resolved, confidence)]`` and unresolved."""
    resolvable: list[tuple[AppEntry, AppEntry, str]] = []
    unresolved: list[AppEntry] = []
    for app in apps:
        resolved, confidence = resolve(app, info)
        if resolved is None:
            unresolved.append(app)
        else:
            resolvable.append((app, resolved, confidence))
    return resolvable, unresolved


def run(installer: Installer, apps: list[AppEntry], info: PlatformInfo,
        on_event: Callable[[str, AppEntry], None] | None = None,
        verify: bool = True) -> RestoreReport:
    """Install every app, verifying presence afterwards. Returns a report.

    ``on_event(stage, app)`` — if given — is called with ``stage`` in
    ``{"installing", "ok", "failed"}`` so a UI can show live progress.
    """
    resolvable, unresolved = plan(apps, info)
    report = RestoreReport(unresolved=unresolved)
    for original, resolved, confidence in resolvable:
        if on_event:
            on_event("installing", resolved)
        installed = installer.install(resolved)
        verified = installer.is_installed(resolved) if verify else None
        result = RestoreResult(original, resolved, confidence, installed, verified)
        report.results.append(result)
        if on_event:
            on_event("ok" if result.ok else "failed", resolved)
    return report
