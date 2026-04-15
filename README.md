# 🔍 App Detector

**Cross-platform application backup & restore tool.**

Never manually reinstall your apps again — App Detector scans your current OS for every installed application, saves the list to a portable manifest file, and lets you restore everything with one command after an OS reinstall.

## Features

- **Cross-platform scanning** — Detects apps from apt, dpkg, snap, flatpak, pacman, dnf (Linux), winget, Chocolatey, Windows Registry (Windows), Homebrew, system_profiler, Mac App Store (macOS)
- **Portable manifest** — JSON file you can store on a USB drive, cloud, or email to yourself
- **Interactive restore** — Pick exactly which apps to reinstall, with version control per-app
- **Dry-run mode** — Preview all install commands before running them
- **Diff & merge** — Compare or combine manifests from different machines
- **Beautiful CLI** — Rich terminal output with progress bars and colour

## Quick Start

### Installation

We recommend using a Python virtual environment to avoid conflicting dependencies.

```bash
# 1. Create a virtual environment
python -m venv .venv

# 2. Activate it
# On Linux/macOS:
source .venv/bin/activate
# On Windows:
# .venv\Scripts\activate

# 3. Install the application (creates the `app-detector` command)
pip install -e .
```

> [!NOTE]
> If `app-detector` returns "command not found", either your virtual environment isn't activated, or your `PATH` is missing your Python scripts directory. You can always run it directly via Python using:
> `python -m app_detector [command]`

### Scan & Export

```bash
# Scan all installed apps and print a summary
app-detector scan

# Export to a portable manifest file
app-detector scan -o my_apps.appdetector.json
```

### Restore

```bash
# Interactive restore — select what to install
app-detector restore my_apps.appdetector.json

# Preview commands without installing
app-detector restore my_apps.appdetector.json --dry-run

# Auto-install everything (no prompts)
app-detector restore my_apps.appdetector.json --auto

# Filter by name
app-detector restore my_apps.appdetector.json --search firefox
```

### Diff & Merge

```bash
# Compare two machines
app-detector diff machine_a.json machine_b.json

# Merge into one
app-detector merge machine_a.json machine_b.json -o combined.json
```

## How It Works

1. **Scan** — Queries every available package manager on your OS
2. **Export** — Saves a JSON manifest with app names, versions, sources, and metadata
3. **Restore** — Reads the manifest, lets you toggle apps on/off, choose version policy (same vs latest), then silently installs via the appropriate package manager

## Supported Package Managers

| OS      | Managers                                          |
|---------|---------------------------------------------------|
| Linux   | apt/dpkg, dnf/rpm, pacman, snap, flatpak          |
| Windows | winget, Chocolatey, Registry detection             |
| macOS   | Homebrew (formula + cask), system_profiler, mas    |

## Running Tests

```bash
pip install pytest
python -m pytest app_detector/tests/ -v
```

## License

MIT
