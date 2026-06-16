"""The live-filter engine: turn a full scanned dataset into a view.

Scanners produce *everything* once; this module re-filters instantly with no
rescan, which is what makes the "scan once, filter live" UX possible.
"""

from __future__ import annotations

from app_detector.models import AppEntry, ScanFilter


def apply_filter(apps: list[AppEntry], flt: ScanFilter) -> list[AppEntry]:
    """Return apps matching *flt*, sorted by installed size (largest first)."""
    matched = [a for a in apps if flt.matches(a)]
    matched.sort(key=lambda a: a.size_bytes, reverse=True)
    return matched


def total_size(apps: list[AppEntry]) -> int:
    return sum(a.size_bytes for a in apps)
