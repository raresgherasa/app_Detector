"""Data model for a detected application."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class AppEntry:
    """Represents a single installed application."""

    name: str                          # Human-readable name ("Firefox")
    package_id: str                    # Package-manager ID ("firefox", "Mozilla.Firefox")
    version: str                      # Currently installed version
    source: str                       # Where it was found ("apt", "snap", "winget", "brew", …)
    category: str = "uncategorised"   # Auto-categorised ("browser", "dev-tool", …)
    is_selected: bool = True          # User toggle for restore
    target_version: str = "latest"    # "same" or "latest"
    metadata: dict[str, Any] = field(default_factory=dict)

    # ── Serialisation helpers ──────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppEntry":
        return cls(**data)

    # ── Display helpers ────────────────────────────────────────────────

    @property
    def display_name(self) -> str:
        """Friendly single-line label."""
        return f"{self.name} {self.version} ({self.source})"

    def __str__(self) -> str:
        status = "✅" if self.is_selected else "☐ "
        ver_label = "latest" if self.target_version == "latest" else f"v{self.target_version}"
        return f"{status}  {self.name:<30s} {self.version:<12s} ({self.source:<10s}) → {ver_label}"
