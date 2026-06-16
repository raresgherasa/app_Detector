"""User overrides for the heuristic Kind classification.

The scanners *guess* whether a package is an App, Tool or Library. When the guess
is wrong, the user can correct it once and have it stick: corrections live in
``overrides.json`` (keyed by ``package_id``) and are re-applied after every scan,
so a fix never has to be made twice.
"""

from __future__ import annotations

import json

from app_detector.models import AppEntry, Kind
from app_detector.util import log
from app_detector.util.paths import config_file

_FILE = "overrides.json"


def _path():
    return config_file(_FILE)


def load() -> dict[str, Kind]:
    """Return the saved ``package_id → Kind`` overrides (empty if none/invalid)."""
    p = _path()
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    out: dict[str, Kind] = {}
    for pid, kind in raw.items():
        try:
            out[pid] = Kind(kind)
        except ValueError:
            continue
    return out


def _save(data: dict[str, Kind]) -> None:
    _path().write_text(
        json.dumps({k: v.value for k, v in data.items()}, indent=2),
        encoding="utf-8")


def set_kind(package_id: str, kind: Kind) -> None:
    data = load()
    data[package_id] = kind
    _save(data)


def clear(package_id: str) -> bool:
    """Remove an override; returns True if one existed."""
    data = load()
    if package_id in data:
        del data[package_id]
        _save(data)
        return True
    return False


def apply(apps: list[AppEntry], overrides: dict[str, Kind] | None = None) -> int:
    """Apply overrides in place, returning how many entries were changed."""
    overrides = load() if overrides is None else overrides
    if not overrides:
        return 0
    changed = 0
    for app in apps:
        new_kind = overrides.get(app.package_id)
        if new_kind is not None and app.kind is not new_kind:
            app.kind = new_kind
            changed += 1
    if changed:
        log.info(f"Applied {changed} classification override(s).")
    return changed
