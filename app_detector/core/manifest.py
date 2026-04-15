"""Manifest — load, save, merge, and validate application snapshots."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app_detector.models.app_entry import AppEntry
from app_detector.utils.platform_detect import PlatformInfo


SCHEMA_VERSION = "1.0"


@dataclass
class Manifest:
    """A portable snapshot of installed applications."""

    schema_version: str = SCHEMA_VERSION
    created_at: str = ""
    source_os: dict[str, Any] = field(default_factory=dict)
    apps: list[AppEntry] = field(default_factory=list)

    # ── Factory ────────────────────────────────────────────────────────

    @classmethod
    def create(cls, apps: list[AppEntry], platform_info: PlatformInfo) -> "Manifest":
        return cls(
            schema_version=SCHEMA_VERSION,
            created_at=datetime.now(timezone.utc).isoformat(),
            source_os={
                "family": platform_info.family,
                "distro": platform_info.distro,
                "hostname": platform_info.hostname,
                "available_managers": platform_info.available_managers,
            },
            apps=apps,
        )

    # ── Serialisation ──────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "source_os": self.source_os,
            "apps": [a.to_dict() for a in self.apps],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Manifest":
        return cls(
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            created_at=data.get("created_at", ""),
            source_os=data.get("source_os", {}),
            apps=[AppEntry.from_dict(a) for a in data.get("apps", [])],
        )

    @classmethod
    def from_json(cls, text: str) -> "Manifest":
        return cls.from_dict(json.loads(text))

    # ── File I/O ───────────────────────────────────────────────────────

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "Manifest":
        text = Path(path).read_text(encoding="utf-8")
        return cls.from_json(text)

    # ── Merge ──────────────────────────────────────────────────────────

    @staticmethod
    def merge(a: "Manifest", b: "Manifest") -> "Manifest":
        """Merge two manifests, de-duplicating by (package_id, source)."""
        seen: set[tuple[str, str]] = set()
        merged: list[AppEntry] = []
        for app in a.apps + b.apps:
            key = (app.package_id.lower(), app.source)
            if key not in seen:
                seen.add(key)
                merged.append(app)

        return Manifest(
            schema_version=SCHEMA_VERSION,
            created_at=datetime.now(timezone.utc).isoformat(),
            source_os=a.source_os,  # keep first manifest's OS info
            apps=merged,
        )

    # ── Convenience ────────────────────────────────────────────────────

    @property
    def selected_apps(self) -> list[AppEntry]:
        return [a for a in self.apps if a.is_selected]

    @property
    def summary(self) -> str:
        total = len(self.apps)
        selected = len(self.selected_apps)
        os_label = self.source_os.get("distro", self.source_os.get("family", "unknown"))
        return f"{total} apps from {os_label} ({selected} selected)"
