"""Core data model: AppEntry, Kind, SizeTier, ScanFilter.

The design centres on two signals the old version ignored, which together separate
"apps worth restoring" from system noise:

* ``manual``      — did the user explicitly install it (vs auto-pulled dependency)?
* ``size_bytes``  — installed size, powering the size tiers.

plus a coarse ``kind`` classification (App / Tool / Library). Scanners populate all
three once; filtering is then a pure, instant operation (see :mod:`filtering`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Kind(str, Enum):
    """What sort of thing a package is."""

    APP = "app"          # GUI / user-facing application
    TOOL = "tool"        # command-line tool / utility
    LIBRARY = "library"  # library, runtime, font, driver, doc, dependency


class SizeTier(Enum):
    """The three size "scans". Value is the minimum installed size in bytes."""

    ALL = 0
    LARGE = 100 * 1024 * 1024     # ≥ 100 MB
    HUGE = 1024 * 1024 * 1024     # ≥ 1 GB

    @classmethod
    def from_name(cls, name: str) -> "SizeTier":
        return cls[name.strip().upper()]


# Package-id suffixes that vary by channel/arch but mean the same app, stripped
# when deriving a cross-manager canonical key.
_CANON_SUFFIXES = ("-stable", "-beta", "-nightly", "-bin", "-git", "-desktop",
                   "-ce", "-oss")


def canonical_key(package_id: str) -> str:
    """Normalise a package id into an OS-agnostic key.

    ``google-chrome-stable`` → ``google-chrome``; ``Mozilla.Firefox`` → ``firefox``;
    ``code`` → ``code``. Best-effort only: it powers a lookup that always falls
    back to the original id, so an imperfect key never breaks a same-OS restore.
    """
    key = package_id.strip().lower()
    # Vendor-prefixed ids (winget "Mozilla.Firefox", choco) → last component.
    if "." in key and "/" not in key:
        key = key.rsplit(".", 1)[-1]
    for suf in _CANON_SUFFIXES:
        if key.endswith(suf):
            key = key[: -len(suf)]
            break
    return key.replace("_", "-")


def human_size(n: int) -> str:
    """Format a byte count as a short human string (e.g. ``1.2 GB``)."""
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(size)} B"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


@dataclass
class AppEntry:
    """A single installed package/application with enrichment metadata."""

    name: str                          # Human-readable name ("Firefox")
    package_id: str                    # Package-manager ID ("firefox", "Mozilla.Firefox")
    version: str = ""                  # Currently installed version
    source: str = ""                   # Where it was found ("apt", "snap", "winget", …)
    size_bytes: int = 0                # Installed size on disk
    kind: Kind = Kind.LIBRARY          # App / Tool / Library
    manual: bool = False               # Explicitly installed by the user
    canonical: str = ""                # OS-agnostic key for cross-manager restore
    is_selected: bool = True           # User toggle for restore
    target_version: str = "latest"     # "same" or "latest"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # A blank canonical (the common case — scanners don't set it) is derived
        # from the package id so cross-manager resolution always has a key.
        if not self.canonical:
            self.canonical = canonical_key(self.package_id or self.name)

    # ── Display helpers ────────────────────────────────────────────────

    @property
    def size_human(self) -> str:
        # A real package is never 0 bytes; treat 0 as "size unknown".
        return "—" if self.size_bytes <= 0 else human_size(self.size_bytes)

    @property
    def display_name(self) -> str:
        return f"{self.name} {self.version} ({self.source})"

    def __str__(self) -> str:
        status = "✓" if self.is_selected else "·"
        return (
            f"{status} {self.name:<32.32s} {self.version:<14.14s} "
            f"{self.size_human:>9s}  {self.kind.value:<8s} ({self.source})"
        )

    # ── Serialisation ──────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["kind"] = self.kind.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppEntry":
        data = dict(data)
        kind = data.get("kind", Kind.LIBRARY.value)
        data["kind"] = Kind(kind) if not isinstance(kind, Kind) else kind
        # Drop unknown keys so older/newer manifests still load.
        allowed = cls.__dataclass_fields__.keys()
        return cls(**{k: v for k, v in data.items() if k in allowed})


@dataclass
class ScanFilter:
    """A live view over a scanned dataset. ``matches`` decides inclusion.

    Defaults encode the recommended view: manually-installed Apps + CLI Tools,
    no size floor, libraries hidden.
    """

    min_size_bytes: int = 0
    kinds: set[Kind] = field(default_factory=lambda: {Kind.APP, Kind.TOOL})
    manual_only: bool = True

    def matches(self, app: AppEntry) -> bool:
        return (
            app.size_bytes >= self.min_size_bytes
            and app.kind in self.kinds
            and (app.manual or not self.manual_only)
        )

    # ── Convenience constructors / serialisation ───────────────────────

    @classmethod
    def from_options(
        cls,
        tier: SizeTier = SizeTier.ALL,
        min_size_bytes: int | None = None,
        kinds: set[Kind] | None = None,
        manual_only: bool = True,
    ) -> "ScanFilter":
        floor = tier.value if min_size_bytes is None else min_size_bytes
        return cls(
            min_size_bytes=floor,
            kinds=kinds if kinds is not None else {Kind.APP, Kind.TOOL},
            manual_only=manual_only,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "min_size_bytes": self.min_size_bytes,
            "kinds": sorted(k.value for k in self.kinds),
            "manual_only": self.manual_only,
        }
