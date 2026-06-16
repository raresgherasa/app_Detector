"""Linux scanner & installer: dpkg/apt, rpm, pacman, snap, flatpak.

The hard part is classification. We combine three cheap signals:

* installed size      — from each package manager
* explicit-install    — ``apt-mark showmanual`` / ``pacman -Qe`` / ``dnf history userinstalled``
* "is it a GUI app?"  — packages that ship a ``.desktop`` launcher

so the default view collapses thousands of dependency libraries down to the
handful of things the user actually chose to install.
"""

from __future__ import annotations

import os
import shlex
import subprocess

from app_detector.models import AppEntry, Kind
from app_detector.platform_detect import _has
from app_detector.scanners.base import Installer, Scanner, run
from app_detector.scanners.system_packages import (
    LINUX_APT_SYSTEM, LINUX_APT_SYSTEM_PREFIXES, LINUX_SNAP_SYSTEM,
)
from app_detector.util import log

# Debian sections that are essentially never user-facing applications.
_LIB_SECTIONS = {
    "libs", "libdevel", "oldlibs", "debug", "fonts", "doc", "localization",
    "kernel", "introspection", "translations", "metapackages",
}

# Name patterns that strongly indicate a library / language module / locale data
# (dictionaries, hyphenation, input-method tables — data, not tools the user runs).
_LIB_PREFIXES = ("lib", "python3-", "python-", "perl-", "golang-", "ruby-",
                 "node-", "fonts-", "gir1.2-",
                 "hunspell-", "hyphen-", "mythes-", "aspell", "ispell",
                 "wbritish", "wamerican", "wcanadian", "witalian", "wngerman",
                 "ibus-table-", "m17n-")
_LIB_SUFFIXES = ("-dev", "-dbg", "-dbgsym", "-doc", "-common", "-data")


def classify(name: str, section: str, is_desktop_app: bool) -> Kind:
    """Decide a package's :class:`Kind` from its name, section and launcher."""
    if is_desktop_app:
        return Kind.APP
    sec = section.lower().rsplit("/", 1)[-1]   # "universe/libs" → "libs"
    n = name.lower()
    if sec in _LIB_SECTIONS:
        return Kind.LIBRARY
    if n.startswith(_LIB_PREFIXES) or n.endswith(_LIB_SUFFIXES):
        return Kind.LIBRARY
    return Kind.TOOL


# ─── Signal collectors ──────────────────────────────────────────────────────

def _manual_set() -> set[str]:
    """Package names the user explicitly installed (apt)."""
    out = run(["apt-mark", "showmanual"])
    return set(out.splitlines()) if out else set()


_APPLICATIONS_DIR = "/usr/share/applications"


def _read_desktop_entry(path: str) -> tuple[str, str, bool]:
    """Return ``(Name, Icon, is_terminal)`` from a ``.desktop`` file's main entry.

    Only the ``[Desktop Entry]`` group is consulted (so per-action names like
    "New Incognito Window" are ignored), and localized ``Name[xx]=`` keys are
    skipped in favour of the plain ``Name=``. Name and Icon may be ``""``.
    ``is_terminal`` is True when ``Terminal=true`` — meaning the app runs inside
    a terminal emulator and should be classified as a tool, not a GUI app.
    """
    name = icon = ""
    is_terminal = False
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            in_entry = False
            for line in fh:
                line = line.strip()
                if line.startswith("["):
                    in_entry = line == "[Desktop Entry]"
                elif in_entry and line.startswith("Name=") and not name:
                    name = line[5:].strip()
                elif in_entry and line.startswith("Icon=") and not icon:
                    icon = line[5:].strip()
                elif in_entry and line.startswith("Terminal="):
                    is_terminal = line[9:].strip().lower() == "true"
    except OSError:
        pass
    return name, icon, is_terminal


def _desktop_app_info() -> dict[str, tuple[str, str]]:
    """Map ``package name → (display name, icon name)`` for packages owning a
    ``.desktop`` launcher (these are treated as GUI apps). The icon name is the
    raw freedesktop ``Icon=`` value, resolved to a file later by the GUI."""
    info: dict[str, tuple[str, str]] = {}
    try:
        files = [
            os.path.join(_APPLICATIONS_DIR, f)
            for f in os.listdir(_APPLICATIONS_DIR)
            if f.endswith(".desktop")
        ]
    except OSError:
        return info
    out = run(["dpkg", "-S", *files]) if files else None
    if not out:
        return info
    # A package can own several launchers (e.g. gnome-control-center panels);
    # collect them all, then pick the one that best represents the package.
    candidates: dict[str, list[str]] = {}
    for line in out.splitlines():
        # Format: "pkg1, pkg2: /usr/share/applications/foo.desktop"
        pkg_part, _, path = line.partition(":")
        path = path.strip()
        if not path:
            continue
        pkg = pkg_part.split(",")[0].strip()
        candidates.setdefault(pkg, []).append(path)
    for pkg, paths in candidates.items():
        # Prefer a launcher whose filename matches the package name.
        paths.sort(key=lambda p: (
            os.path.splitext(os.path.basename(p))[0] != pkg, len(p)))
        name, icon, is_terminal = _read_desktop_entry(paths[0])
        if is_terminal:
            continue  # runs in a terminal — classify as TOOL, not APP
        info[pkg] = (name or _prettify(pkg), icon)
    return info


# Suffixes stripped when prettifying a bare package id into a display name.
_PRETTIFY_SUFFIXES = ("-stable", "-beta", "-nightly", "-bin", "-git", "-desktop")


def _prettify(pkg: str) -> str:
    """Best-effort human name from a package id: ``google-chrome-stable`` →
    ``Google Chrome``. Used only as a fallback when no ``.desktop`` name exists."""
    base = pkg
    for suf in _PRETTIFY_SUFFIXES:
        if base.endswith(suf):
            base = base[: -len(suf)]
            break
    base = base.replace("-", " ").replace("_", " ").strip()
    return base.title() if base else pkg


# ─── Per-manager scanners ───────────────────────────────────────────────────

# dpkg ``Priority`` values that mark a package as part of the base OS install.
# The Ubuntu installer seeds these as "manually installed", so apt-mark alone
# can't tell them from things the user actually chose — Priority can.
_BASE_PRIORITIES = {"required", "important", "standard"}


def _scan_dpkg() -> list[AppEntry]:
    if not _has("dpkg-query"):
        return []
    fmt = (r"${Package}\t${Version}\t${Installed-Size}\t${Section}"
           r"\t${Priority}\t${binary:Summary}\n")
    try:
        res = subprocess.run(["dpkg-query", "-W", f"-f={fmt}"],
                             capture_output=True, text=True, timeout=30)
        if res.returncode != 0:
            return []
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return []

    manual = _manual_set()
    desktop_info = _desktop_app_info()

    entries: list[AppEntry] = []
    for line in res.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 6:
            continue
        name, ver, size_kb, section, priority, summary = parts[:6]
        if name in LINUX_APT_SYSTEM or name.startswith(LINUX_APT_SYSTEM_PREFIXES):
            continue
        try:
            size_bytes = int(size_kb) * 1024  # dpkg reports KiB
        except ValueError:
            size_bytes = 0
        kind = classify(name, section, name in desktop_info)
        # GUI apps get a friendly name + real icon; tools/libraries keep their
        # real id (which is what you'd type to install them).
        friendly, icon = desktop_info.get(name, (name, ""))
        display = friendly if kind == Kind.APP else name
        meta = {"section": section, "description": summary}
        if icon:
            meta["icon"] = icon
        # A base-system package was put there by the OS, not chosen by the user —
        # never treat it as a manual install, even if apt-mark says so.
        is_base = priority.strip().lower() in _BASE_PRIORITIES
        entries.append(AppEntry(
            name=display, package_id=name, version=ver, source="apt",
            size_bytes=size_bytes, kind=kind,
            manual=(name in manual) and not is_base,
            metadata=meta,
        ))
    return entries


def _scan_rpm() -> list[AppEntry]:
    if not _has("rpm"):
        return []
    fmt = "%{NAME}\t%{VERSION}\t%{SIZE}\t%{GROUP}\t%{SUMMARY}\n"
    out = run(["rpm", "-qa", "--queryformat", fmt])
    if not out:
        return []
    manual: set[str] = set()
    uout = run(["dnf", "repoquery", "--userinstalled", "--qf", "%{name}"])
    if uout:
        manual = set(uout.splitlines())
    entries: list[AppEntry] = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 5:
            continue
        name, ver, size, group, summary = parts[:5]
        try:
            size_bytes = int(size)
        except ValueError:
            size_bytes = 0
        entries.append(AppEntry(
            name=name, package_id=name, version=ver, source="dnf",
            size_bytes=size_bytes,
            kind=classify(name, group, False),
            manual=(name in manual) if manual else True,
            metadata={"group": group, "description": summary},
        ))
    return entries


def _scan_pacman() -> list[AppEntry]:
    out = run(["pacman", "-Q"])
    if not out:
        return []
    explicit = set()
    eout = run(["pacman", "-Qqe"])
    if eout:
        explicit = set(eout.splitlines())
    # Installed sizes (KiB) via expac if available, else skip sizing.
    sizes: dict[str, int] = {}
    sout = run(["expac", "-Q", "%n\t%m"])
    if sout:
        for line in sout.splitlines():
            n, _, s = line.partition("\t")
            try:
                sizes[n] = int(s)
            except ValueError:
                pass
    entries: list[AppEntry] = []
    for line in out.splitlines():
        parts = line.split(None, 1)
        if not parts:
            continue
        name = parts[0]
        ver = parts[1] if len(parts) > 1 else ""
        entries.append(AppEntry(
            name=name, package_id=name, version=ver, source="pacman",
            size_bytes=sizes.get(name, 0),
            kind=classify(name, "", False),
            manual=name in explicit,
        ))
    return entries


_SNAPS_DIR = "/var/lib/snapd/snaps"

# Snap base runtimes / infrastructure — present as dependencies, not user apps.
_SNAP_BASES = {"core", "core16", "core18", "core20", "core22", "core24",
               "bare", "snapd"}
# Prefixes of platform / content snaps auto-pulled as shared runtimes.
_SNAP_RUNTIME_PREFIXES = ("gnome-", "kde-", "gtk-common-themes", "mesa",
                          "ffmpeg-", "kf5-", "kf6-", "gaming-graphics-")


def _is_snap_runtime(name: str, notes: str) -> bool:
    return (name in _SNAP_BASES
            or name.startswith(_SNAP_RUNTIME_PREFIXES)
            or "base" in notes or "snapd" in notes)


def _snap_size(name: str, rev: str) -> int:
    """Installed size of a snap = size of its squashfs ``<name>_<rev>.snap``."""
    try:
        return os.path.getsize(os.path.join(_SNAPS_DIR, f"{name}_{rev}.snap"))
    except OSError:
        return 0


_SNAP_DESKTOP_DIR = "/var/lib/snapd/desktop/applications"


def _snap_desktop(name: str) -> tuple[str, str]:
    """``(display name, icon)`` from a snap's ``<name>_<name>.desktop``, if any.

    The snap's own ``Name=`` ("Launcher for Minecraft") is far better than a
    prettified package id ("Launcher Ot Minecraft"). Either field may be ``""``.
    Snaps reference their icon by absolute path, which ``find_icon`` accepts.
    """
    for cand in (f"{name}_{name}.desktop", f"{name}_{name}-app.desktop"):
        path = os.path.join(_SNAP_DESKTOP_DIR, cand)
        if os.path.exists(path):
            disp, icon, _ = _read_desktop_entry(path)
            if disp or icon:
                return disp, icon
    return "", ""


def _scan_snap() -> list[AppEntry]:
    out = run(["snap", "list"])
    if not out:
        return []
    lines = out.splitlines()
    if len(lines) < 2:
        return []
    entries: list[AppEntry] = []
    for line in lines[1:]:
        cols = line.split()
        if len(cols) < 3:
            continue
        name, ver, rev = cols[0], cols[1], cols[2]
        channel = cols[3] if len(cols) > 3 else ""
        notes = cols[5] if len(cols) > 5 else ""
        if name in LINUX_SNAP_SYSTEM:
            continue
        is_runtime = _is_snap_runtime(name, notes)
        meta: dict = {"channel": channel} if channel else {}
        display = name
        if not is_runtime:
            disp, icon = _snap_desktop(name)
            display = disp or _prettify(name)
            if icon:
                meta["icon"] = icon
        entries.append(AppEntry(
            name=display,
            package_id=name, version=ver, source="snap",
            size_bytes=_snap_size(name, rev),
            kind=Kind.LIBRARY if is_runtime else Kind.APP,
            manual=not is_runtime,
            metadata=meta,
        ))
    return entries


def _scan_flatpak() -> list[AppEntry]:
    out = run(["flatpak", "list", "--app",
               "--columns=application,version,name,size"])
    if not out:
        return []
    entries: list[AppEntry] = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        app_id = parts[0].strip()
        ver = parts[1].strip() if len(parts) > 1 else ""
        display = parts[2].strip() if len(parts) > 2 else app_id
        size_bytes = _parse_flatpak_size(parts[3].strip()) if len(parts) > 3 else 0
        entries.append(AppEntry(
            name=display, package_id=app_id, version=ver, source="flatpak",
            size_bytes=size_bytes, kind=Kind.APP, manual=True,
        ))
    return entries


def _parse_flatpak_size(text: str) -> int:
    """Parse flatpak's human size column (e.g. ``1.2 GB``) into bytes."""
    text = text.strip()
    if not text:
        return 0
    units = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4,
             "KIB": 1024, "MIB": 1024**2, "GIB": 1024**3}
    parts = text.split()
    try:
        if len(parts) == 2:
            return int(float(parts[0]) * units.get(parts[1].upper(), 1))
        return int(float(text))
    except ValueError:
        return 0


# ─── Manually-installed (non-package) GUI apps ───────────────────────────────
#
# Apps installed by downloading an installer/tarball (e.g. into ``/opt`` or the
# home directory) are unknown to every package manager, so the scanners above
# miss them entirely. They almost always drop a ``.desktop`` launcher, though —
# so we sweep the XDG application directories, discard launchers a package
# already owns (those are reported above) and surface the rest as real apps.


def _xdg_app_dirs() -> list[str]:
    """Standard directories that hold ``.desktop`` launchers, de-duplicated.

    Covers the system dirs plus the per-user ``~/.local/share/applications``.
    The canonical locations (derived from ``$HOME``) are always included so the
    scan works even when launched from inside a Snap/Flatpak sandbox, whose
    ``XDG_DATA_*`` env vars point at private dirs. Snap/Flatpak export dirs are
    excluded — those apps are already scanned natively.
    """
    home = os.path.expanduser("~")
    # Canonical bases first, then anything extra the environment advertises.
    bases = [os.path.join(home, ".local/share"), "/usr/local/share", "/usr/share"]
    data_home = os.environ.get("XDG_DATA_HOME")
    if data_home:
        bases.append(data_home)
    bases += (os.environ.get("XDG_DATA_DIRS") or "").split(":")
    seen: list[str] = []
    for base in bases:
        if not base:
            continue
        d = os.path.join(base, "applications")
        # Skip sandbox/export dirs (a snap-launched shell injects these).
        if d in seen or any(s in d for s in ("/snap/", "flatpak", "snapd")):
            continue
        seen.append(d)
    return seen


def _dpkg_owned(paths: list[str]) -> set[str]:
    """Subset of *paths* that ``dpkg`` reports as owned by an installed package.

    ``dpkg -S`` exits non-zero when *any* path is unowned, so we read its stdout
    directly rather than via :func:`run` (which would discard it on failure).
    """
    if not _has("dpkg") or not paths:
        return set()
    try:
        res = subprocess.run(["dpkg", "-S", *paths],
                             capture_output=True, text=True, timeout=30)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return set()
    owned: set[str] = set()
    for line in res.stdout.splitlines():
        # "pkg1, pkg2: /usr/share/applications/foo.desktop"
        _, _, path = line.rpartition(": ")
        if path:
            owned.add(path.strip())
    return owned


def _read_desktop_full(path: str) -> dict[str, str]:
    """Parse the ``[Desktop Entry]`` group into a ``{key: value}`` dict."""
    data: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            in_entry = False
            for line in fh:
                line = line.strip()
                if line.startswith("["):
                    in_entry = line == "[Desktop Entry]"
                elif in_entry and "=" in line and not line.startswith("#"):
                    key, _, val = line.partition("=")
                    data.setdefault(key.strip(), val.strip())
    except OSError:
        pass
    return data


# Launcher names that are secondary tools of a bigger install, not the app
# itself (an install dir often ships several: updater, uninstaller, …).
_HELPER_KEYWORDS = ("update", "uninstall", "installer", "product selector",
                    "selector", "shape editor", "reset", "safe mode",
                    "diagnostic", "repair")


# Generic home folders that are never an app's private install dir — guard
# against ``du``-ing (say) the whole Desktop for a launcher dropped there.
_GENERIC_HOME_DIRS = {"Desktop", "Documents", "Downloads", "Music", "Pictures",
                      "Videos", "Public", "Templates", "snap", "bin", "tmp"}


def _install_root(exec_field: str) -> str:
    """Self-contained install dir for an Exec line, or ``""`` if not one.

    ``/opt/antigravity/antigravity %U`` → ``/opt/antigravity``;
    ``"/home/u/Visual_Paradigm/bin/vp" %U`` → ``/home/u/Visual_Paradigm``.
    Binaries in shared dirs (``/usr/bin`` …) or generic home folders
    (``~/Desktop`` …) have no private root and return ``""``.
    """
    try:
        tokens = shlex.split(exec_field)
    except ValueError:
        tokens = exec_field.split()
    if not tokens:
        return ""
    real = os.path.realpath(tokens[0])
    home = os.path.expanduser("~")
    for base in ("/opt", home):
        prefix = base + "/"
        if real.startswith(prefix):
            top = real[len(prefix):].split("/", 1)[0]
            if top and not top.startswith(".") and top not in _GENERIC_HOME_DIRS:
                return os.path.join(base, top)
    return ""


def _du_kib(path: str) -> int:
    out = run(["du", "-sk", path])
    if not out:
        return 0
    try:
        return int(out.split()[0]) * 1024
    except (ValueError, IndexError):
        return 0


def _is_pm_relauncher(exec_field: str) -> bool:
    """True if an Exec line merely re-launches a snap/flatpak app.

    Such launchers (often user copies tweaked for e.g. a discrete GPU) point at
    an app another scanner already owns, so the catch-all must not list them.
    """
    e = exec_field.lower()
    return ("snap run " in e or "/snap/bin/" in e
            or "flatpak run " in e or "/var/lib/flatpak/" in e)


def _scan_desktop_apps() -> list[AppEntry]:
    """Detect manually-installed GUI apps via their orphan ``.desktop`` files."""
    # Gather every launcher across the XDG dirs.
    files: list[str] = []
    for d in _xdg_app_dirs():
        try:
            files += [os.path.join(d, f) for f in os.listdir(d)
                      if f.endswith(".desktop")]
        except OSError:
            continue
    if not files:
        return []

    owned = _dpkg_owned(files)

    # Group surviving launchers by install root so an app that ships several
    # launchers (app + updater + …) collapses to a single entry.
    groups: dict[str, list[tuple[str, dict[str, str]]]] = {}
    for path in files:
        if path in owned:
            continue
        d = _read_desktop_full(path)
        if (d.get("Type", "Application") != "Application"
                or d.get("NoDisplay", "").lower() == "true"
                or d.get("Hidden", "").lower() == "true"
                or not d.get("Name")
                or _is_pm_relauncher(d.get("Exec", ""))):
            continue
        root = _install_root(d.get("Exec", ""))
        key = root or path   # rootless launchers stay independent
        groups.setdefault(key, []).append((path, d))

    entries: list[AppEntry] = []
    for key, members in groups.items():
        # Pick the entry that best represents the app: a non-helper launcher
        # with the shortest name (e.g. "Visual Paradigm" over "…Updater").
        path, d = min(members, key=lambda m: (
            any(k in m[1]["Name"].lower() for k in _HELPER_KEYWORDS),
            len(m[1]["Name"])))
        name = d["Name"].replace("_", " ").strip()
        root = key if os.path.isabs(key) and os.path.isdir(key) else ""
        is_terminal = d.get("Terminal", "").lower() == "true"
        meta: dict = {}
        if d.get("Icon"):
            meta["icon"] = d["Icon"]
        if root:
            meta["path"] = root
        entries.append(AppEntry(
            name=name,
            package_id=os.path.basename(root) if root else name,
            source="local",
            size_bytes=_du_kib(root) if root else 0,
            kind=Kind.TOOL if is_terminal else Kind.APP,
            manual=True,
            metadata=meta,
        ))
    return entries


# ─── Unified detector ───────────────────────────────────────────────────────

class LinuxScanner(Scanner):
    # ``None`` binary → scanner has no package-manager dependency, always runs.
    SCANNERS = [
        ("dpkg-query", _scan_dpkg),
        ("rpm", _scan_rpm),
        ("pacman", _scan_pacman),
        ("snap", _scan_snap),
        ("flatpak", _scan_flatpak),
        (None, _scan_desktop_apps),
    ]

    def name(self) -> str:
        return "linux"

    def scan_all(self) -> list[AppEntry]:
        found: list[AppEntry] = []
        seen: set[tuple[str, str]] = set()
        for binary, fn in self.SCANNERS:
            if binary and not _has(binary):
                continue
            label = binary.split("-")[0] if binary else "local apps"
            log.info(f"Scanning [bold]{label}[/bold] …")
            # The catch-all may rediscover a package app via its launcher; keep
            # the earlier package-manager entry (richer) and drop the duplicate.
            fresh = [a for a in fn()
                     if (a.package_id.lower(), a.name.lower()) not in seen]
            seen.update((a.package_id.lower(), a.name.lower()) for a in fresh)
            log.success(f"{label}: {len(fresh)} items")
            found.extend(fresh)
        return found


# ─── Installer ──────────────────────────────────────────────────────────────

class LinuxInstaller(Installer):
    def install_command(self, app: AppEntry) -> list[str]:
        src, pkg = app.source, app.package_id
        ver = app.version if app.target_version == "same" else None
        if src == "apt":
            target = f"{pkg}={ver}" if ver else pkg
            return ["sudo", "apt", "install", "-y", target]
        if src in ("dnf", "rpm"):
            target = f"{pkg}-{ver}" if ver else pkg
            return ["sudo", "dnf", "install", "-y", target]
        if src == "pacman":
            return ["sudo", "pacman", "-S", "--noconfirm", pkg]
        if src == "snap":
            cmd = ["sudo", "snap", "install", pkg]
            ch = app.metadata.get("channel")
            if ch:
                cmd += ["--channel", ch]
            return cmd
        if src == "flatpak":
            return ["flatpak", "install", "-y", pkg]
        return ["echo", f"No installer for source '{src}'"]

    def install(self, app: AppEntry, silent: bool = True) -> bool:
        return self._run_install(app, self.install_command(app), silent)

    def is_installed(self, app: AppEntry) -> bool | None:
        src, pkg = app.source, app.package_id
        if src == "apt":
            return run(["dpkg-query", "-W", "-f=${Status}", pkg]) is not None \
                if _has("dpkg-query") else None
        if src in ("dnf", "rpm"):
            return run(["rpm", "-q", pkg]) is not None if _has("rpm") else None
        if src == "pacman":
            return run(["pacman", "-Q", pkg]) is not None if _has("pacman") else None
        if src == "snap":
            return run(["snap", "list", pkg]) is not None if _has("snap") else None
        if src == "flatpak":
            return run(["flatpak", "info", pkg]) is not None if _has("flatpak") else None
        if src == "local":
            path = app.metadata.get("path")
            return os.path.isdir(path) if path else None
        return None
