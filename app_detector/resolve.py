"""Cross-manager restore resolution.

A manifest records *where* an app came from (``source="apt"``, ``package_id``).
Restoring it verbatim only works when the target machine has the same package
manager. This module maps an app to whatever manager the *target* actually has,
so an apt snapshot can reinstall via dnf / brew / winget on a fresh OS.

Resolution is honest and best-effort, returning one of three confidences:

* ``exact``  — the app's own manager is available on the target; install as-is.
* ``mapped`` — found in the curated cross-manager alias table.
* ``guess``  — no alias known, but the package name often matches across managers
               (``git``, ``htop``, …); we try the target's primary manager.

When none of these apply, resolution returns ``None`` and the caller flags the
app as unrestorable on this OS rather than silently failing.
"""

from __future__ import annotations

from dataclasses import replace

from app_detector.models import AppEntry, canonical_key
from app_detector.platform_detect import PlatformInfo

# A "source" is how the installers dispatch; this is the binary that must exist
# on the target for that source to be usable.
SOURCE_BINARY: dict[str, str] = {
    "apt": "apt", "dnf": "dnf", "rpm": "dnf", "pacman": "pacman",
    "snap": "snap", "flatpak": "flatpak",
    "brew": "brew", "brew-cask": "brew", "system": "brew", "mas": "mas",
    "winget": "winget", "registry": "winget", "choco": "choco",
}

# Preferred install source per OS family, best first.
PLATFORM_SOURCES: dict[str, list[str]] = {
    "linux": ["apt", "dnf", "pacman", "flatpak", "snap"],
    "darwin": ["brew-cask", "brew"],
    "windows": ["winget", "choco"],
}

# Curated cross-manager equivalences. Each group maps a source → its package id
# for one logical app. Add rows here to teach the tool new cross-OS mappings.
ALIASES: list[dict[str, str]] = [
    {"apt": "firefox", "dnf": "firefox", "pacman": "firefox", "snap": "firefox",
     "flatpak": "org.mozilla.firefox", "brew-cask": "firefox",
     "winget": "Mozilla.Firefox", "choco": "firefox"},
    {"apt": "code", "dnf": "code", "snap": "code",
     "flatpak": "com.visualstudio.code", "brew-cask": "visual-studio-code",
     "winget": "Microsoft.VisualStudioCode", "choco": "vscode"},
    {"apt": "google-chrome-stable", "dnf": "google-chrome-stable",
     "flatpak": "com.google.Chrome", "brew-cask": "google-chrome",
     "winget": "Google.Chrome", "choco": "googlechrome"},
    {"apt": "chromium-browser", "dnf": "chromium", "pacman": "chromium",
     "snap": "chromium", "flatpak": "org.chromium.Chromium",
     "brew-cask": "chromium", "choco": "chromium"},
    {"apt": "vlc", "dnf": "vlc", "pacman": "vlc", "snap": "vlc",
     "flatpak": "org.videolan.VLC", "brew-cask": "vlc",
     "winget": "VideoLAN.VLC", "choco": "vlc"},
    {"apt": "gimp", "dnf": "gimp", "pacman": "gimp",
     "flatpak": "org.gimp.GIMP", "brew-cask": "gimp",
     "winget": "GIMP.GIMP", "choco": "gimp"},
    {"apt": "inkscape", "dnf": "inkscape", "pacman": "inkscape",
     "flatpak": "org.inkscape.Inkscape", "brew-cask": "inkscape",
     "winget": "Inkscape.Inkscape", "choco": "inkscape"},
    {"apt": "blender", "dnf": "blender", "snap": "blender",
     "flatpak": "org.blender.Blender", "brew-cask": "blender",
     "winget": "BlenderFoundation.Blender", "choco": "blender"},
    {"apt": "git", "dnf": "git", "pacman": "git", "brew": "git",
     "winget": "Git.Git", "choco": "git"},
    {"apt": "nodejs", "dnf": "nodejs", "pacman": "nodejs", "brew": "node",
     "winget": "OpenJS.NodeJS", "choco": "nodejs"},
    {"apt": "docker.io", "dnf": "docker", "pacman": "docker", "brew": "docker",
     "winget": "Docker.DockerDesktop", "choco": "docker-desktop"},
    {"apt": "vim", "dnf": "vim", "pacman": "vim", "brew": "vim",
     "winget": "vim.vim", "choco": "vim"},
    {"apt": "neovim", "dnf": "neovim", "pacman": "neovim", "brew": "neovim",
     "winget": "Neovim.Neovim", "choco": "neovim"},
    {"apt": "spotify-client", "snap": "spotify",
     "flatpak": "com.spotify.Client", "brew-cask": "spotify",
     "winget": "Spotify.Spotify", "choco": "spotify"},
    {"apt": "slack-desktop", "snap": "slack", "flatpak": "com.slack.Slack",
     "brew-cask": "slack", "winget": "SlackTechnologies.Slack", "choco": "slack"},
    {"snap": "discord", "flatpak": "com.discordapp.Discord",
     "brew-cask": "discord", "winget": "Discord.Discord", "choco": "discord"},
    {"apt": "obs-studio", "dnf": "obs-studio", "pacman": "obs-studio",
     "flatpak": "com.obsproject.Studio", "brew-cask": "obs",
     "winget": "OBSProject.OBSStudio", "choco": "obs-studio"},
    {"apt": "libreoffice", "dnf": "libreoffice", "snap": "libreoffice",
     "flatpak": "org.libreoffice.LibreOffice", "brew-cask": "libreoffice",
     "winget": "TheDocumentFoundation.LibreOffice", "choco": "libreoffice-fresh"},
    {"apt": "thunderbird", "dnf": "thunderbird", "snap": "thunderbird",
     "flatpak": "org.mozilla.Thunderbird", "brew-cask": "thunderbird",
     "winget": "Mozilla.Thunderbird", "choco": "thunderbird"},
    {"apt": "keepassxc", "dnf": "keepassxc", "pacman": "keepassxc",
     "flatpak": "org.keepassxc.KeePassXC", "brew-cask": "keepassxc",
     "winget": "KeePassXCTeam.KeePassXC", "choco": "keepassxc"},
    {"apt": "audacity", "dnf": "audacity", "snap": "audacity",
     "flatpak": "org.audacityteam.Audacity", "brew-cask": "audacity",
     "winget": "Audacity.Audacity", "choco": "audacity"},
    {"apt": "steam-installer", "snap": "steam",
     "flatpak": "com.valvesoftware.Steam", "brew-cask": "steam",
     "winget": "Valve.Steam", "choco": "steam"},
]


def _build_index() -> dict[str, dict[str, str]]:
    """Map every known package id (and its canonical key) → its alias group."""
    index: dict[str, dict[str, str]] = {}
    for group in ALIASES:
        for pid in group.values():
            index.setdefault(pid.lower(), group)
            index.setdefault(canonical_key(pid), group)
    return index


_INDEX = _build_index()


def _available_sources(info: PlatformInfo) -> list[str]:
    """Target's installable sources, in preference order, that it actually has."""
    have = set(info.available_managers)
    return [s for s in PLATFORM_SOURCES.get(info.family, [])
            if SOURCE_BINARY.get(s) in have]


def resolve(app: AppEntry, info: PlatformInfo) -> tuple[AppEntry | None, str]:
    """Resolve *app* to something installable on *info*.

    Returns ``(resolved_app, confidence)`` where confidence is
    ``exact`` | ``mapped`` | ``guess``, or ``(None, "unresolved")`` when the app
    cannot be installed on this OS with any known manager.
    """
    have = set(info.available_managers)

    # 1. Same manager present → install verbatim.
    if SOURCE_BINARY.get(app.source) in have:
        return app, "exact"

    targets = _available_sources(info)
    if not targets:
        return None, "unresolved"

    # 2. Curated alias for a manager the target has.
    group = (_INDEX.get(app.package_id.lower())
             or _INDEX.get(app.canonical)
             or _INDEX.get(canonical_key(app.package_id)))
    if group:
        for src in targets:
            if src in group:
                return replace(app, source=src, package_id=group[src],
                               target_version="latest"), "mapped"

    # 3. Guess: many tool names are identical across managers. Vendor-dotted ids
    #    (winget "Mozilla.Firefox") are too manager-specific to guess from.
    if "." not in app.package_id:
        return replace(app, source=targets[0], package_id=app.canonical,
                       target_version="latest"), "guess"

    return None, "unresolved"
