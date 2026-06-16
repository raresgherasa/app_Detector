"""Compare two collections of apps — by manifest, or against the live machine.

Identity is the OS-agnostic :pyattr:`AppEntry.canonical` key so a snapshot taken
under apt and a live Arch system still line up (both ``firefox`` → ``firefox``).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app_detector.models import AppEntry


@dataclass
class Comparison:
    only_a: list[AppEntry] = field(default_factory=list)  # in A, not in B
    only_b: list[AppEntry] = field(default_factory=list)  # in B, not in A
    common: list[AppEntry] = field(default_factory=list)  # in both (A's entry)


def _key(app: AppEntry) -> str:
    return app.canonical or app.package_id.lower()


def compare(a: list[AppEntry], b: list[AppEntry]) -> Comparison:
    """Set-difference *a* vs *b* keyed by canonical identity."""
    b_keys = {_key(x) for x in b}
    a_keys = {_key(x) for x in a}
    return Comparison(
        only_a=[x for x in a if _key(x) not in b_keys],
        only_b=[x for x in b if _key(x) not in a_keys],
        common=[x for x in a if _key(x) in b_keys],
    )
