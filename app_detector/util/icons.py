"""Resolve a freedesktop ``Icon=`` name to a real raster icon file on disk.

`.desktop` launchers reference their icon either by an absolute path or by a
*name* (e.g. ``google-chrome``) that must be looked up against the installed
icon themes. We don't ship an SVG rasteriser, so this resolver only returns
**raster** files (PNG / XPM) — callers fall back to a letter badge when a name
resolves to SVG-only or to nothing at all. On this Ubuntu the Yaru theme ships
PNGs for the GNOME apps whose hicolor entries are SVG-only, so coverage is good.

Results are cached: icon lookups touch the filesystem and the same names recur
across thousands of packages.
"""

from __future__ import annotations

import glob
import os
from functools import lru_cache

# Base directories, most-specific first (user overrides system).
_BASE_DIRS = [
    os.path.expanduser("~/.local/share/icons"),
    "/usr/local/share/icons",
    "/usr/share/icons",
    "/usr/share/pixmaps",
]
# Themes worth searching, in preference order. Yaru (Ubuntu) and Adwaita carry
# PNGs for many apps that only have SVGs under hicolor.
_THEMES = ["Yaru", "Adwaita", "hicolor", "Humanity", "gnome", "Papirus"]
# Sizes preferred for a ~40 px badge: big enough to downscale cleanly, not huge.
_SIZES = ["256x256", "128x128", "96x96", "64x64", "48x48", "32x32"]
_RASTER_EXT = (".png", ".xpm")


@lru_cache(maxsize=4096)
def find_icon(name: str) -> str | None:
    """Return a path to a raster icon for ``name``, or ``None`` if unresolved.

    SVG-only icons return ``None`` on purpose — we have no rasteriser, so the
    caller should fall back to the letter badge rather than fail to load.
    """
    if not name:
        return None
    # Absolute path straight from the .desktop file.
    if os.path.isabs(name):
        return name if os.path.exists(name) and name.endswith(_RASTER_EXT) else None

    for base in _BASE_DIRS:
        if not os.path.isdir(base):
            continue
        # Flat directories like /usr/share/pixmaps.
        for ext in _RASTER_EXT:
            flat = os.path.join(base, name + ext)
            if os.path.exists(flat):
                return flat
        # Themed: <base>/<theme>/<size>/<category>/<name>.<ext>
        for theme in _THEMES:
            theme_dir = os.path.join(base, theme)
            if not os.path.isdir(theme_dir):
                continue
            for size in _SIZES:
                for ext in _RASTER_EXT:
                    matches = glob.glob(
                        os.path.join(theme_dir, size, "*", name + ext))
                    if matches:
                        return matches[0]
    return None
