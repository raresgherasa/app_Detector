"""Known pre-installed system packages per platform.

Excluded from scan results because they will be present on any fresh OS
install and do not need to appear in the user's restore list.
"""

# Ubuntu / Debian default desktop packages — covers 22.04 and 24.04 LTS.
# Both GNOME app names are included because the defaults changed between releases.
LINUX_APT_SYSTEM: frozenset[str] = frozenset({
    # GNOME core apps
    "nautilus", "gedit", "gnome-text-editor", "gnome-calculator",
    "gnome-calendar", "gnome-clocks", "gnome-contacts", "gnome-maps",
    "gnome-weather", "gnome-screenshot", "gnome-disk-utility",
    "gnome-system-monitor", "gnome-terminal", "gnome-console",
    "gnome-font-viewer", "gnome-logs", "gnome-software",
    "gnome-control-center",
    # Media / photos
    "rhythmbox", "totem", "cheese", "eog", "loupe", "shotwell",
    # Documents / archives
    "evince", "file-roller", "baobab",
    # LibreOffice suite (pre-installed on Ubuntu Desktop)
    "libreoffice-writer", "libreoffice-calc", "libreoffice-impress",
    "libreoffice-base", "libreoffice-draw", "libreoffice-math",
    # System audio / Bluetooth daemons & controls (not user-installable apps)
    "pulseaudio", "pipewire", "pavucontrol",
    # Boot / firmware infrastructure (optional priority, but pure system)
    "efibootmgr", "mokutil", "os-prober", "shim-signed", "fwupd",
    # Other Ubuntu defaults
    "simple-scan", "yelp", "deja-dup", "thunderbird",
    # Meta / shell packages
    "ubuntu-desktop", "ubuntu-desktop-minimal", "ubuntu-desktop-bootstrap",
    "gnome-shell",
})

# Package-name prefixes that are always OS/boot infrastructure, never user apps
# (these sit at "optional" priority so the Priority heuristic alone misses them).
LINUX_APT_SYSTEM_PREFIXES: tuple[str, ...] = (
    "grub", "shim", "linux-image-", "linux-headers-", "linux-modules",
)

# Ubuntu-specific pre-installed snaps (user-facing, but shipped by default).
LINUX_SNAP_SYSTEM: frozenset[str] = frozenset({
    "firefox",                    # default browser snap since Ubuntu 22.04
    "thunderbird",                # default mail snap since Ubuntu 24.04
    "snap-store",                 # Ubuntu Software
    "canonical-livepatch",        # Canonical kernel patch service
    "firmware-updater",           # Ubuntu firmware update tool (fwupd front-end)
    "snapd-desktop-integration",  # snapd↔desktop bridge, shipped by Ubuntu
})

# Windows built-in app names — lowercased for case-insensitive exact matching.
WINDOWS_BUILTIN_EXACT: frozenset[str] = frozenset({
    "cortana", "microsoft edge", "photos", "movies & tv",
    "groove music", "windows media player", "mail and calendar",
    "people", "maps", "sticky notes", "alarms & clock",
    "camera", "get started", "xbox", "xbox game bar",
    "xbox live in-game experience", "xbox identity provider",
    "xbox game speech window", "paint", "notepad", "wordpad",
    "snipping tool", "calculator", "windows calculator",
    "microsoft news", "news", "weather", "microsoft weather",
    "solitaire & casual games", "microsoft solitaire collection",
    "feedback hub", "your phone", "phone link",
    "windows store", "microsoft store", "onedrive",
    "microsoft teams", "teams", "skype",
})

# Prefix patterns for Windows entries that embed version numbers in their names.
WINDOWS_BUILTIN_PREFIXES: tuple[str, ...] = (
    "microsoft visual c++",
    "microsoft .net",
    ".net framework",
    "windows software development kit",
    "windows app sdk",
    "windows desktop runtime",
)

# macOS apps shipped by Apple in /System/Applications/ or /Applications/.
MACOS_SYSTEM_APPS: frozenset[str] = frozenset({
    "safari", "mail", "photos", "music", "tv", "podcasts", "news",
    "maps", "calendar", "contacts", "reminders", "notes", "messages",
    "facetime", "app store", "system preferences", "system settings",
    "preview", "textedit", "quicktime player", "font book",
    "chess", "dictionary", "calculator", "automator", "script editor",
    "terminal", "activity monitor", "console", "disk utility", "grapher",
    "airport utility", "boot camp assistant", "colorsync utility",
    "directory utility", "migration assistant", "network utility",
    "voiceover utility", "wireless diagnostics", "books",
    "itunes", "garageband", "imovie", "keynote", "numbers", "pages",
    "finder", "image capture", "time machine", "siri", "stickies",
    "stocks", "home", "shortcuts", "digital color meter",
})
