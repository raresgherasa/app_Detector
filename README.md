# 🔍 App Detector

**Size & kind aware backup / restore tool for installed applications.**

Reinstalling your OS? App Detector scans your machine, shows you the apps **you
actually installed** — filtered by size and kind — saves them to a portable
snapshot, and reinstalls them on the fresh system.

## Why it's different

A naive package scan is useless: on a typical Ubuntu box `dpkg` lists **~2800
packages**, almost all of them low-level libraries, fonts and drivers you never
chose to install. App Detector enriches every package with three signals and lets
you filter on them live:

| Signal | What it answers | Source |
|--------|-----------------|--------|
| **manual** | Did *you* install it, or was it pulled in as a dependency? | `apt-mark showmanual`, `pacman -Qe`, `dnf userinstalled`, `brew leaves` |
| **size** | How big is it on disk? | dpkg `Installed-Size`, rpm `%{SIZE}`, registry `EstimatedSize`, `du` |
| **kind** | App, CLI tool, or library? | `.desktop` launchers + package section + name |

On the same ~2800-package box, the default view collapses to roughly the **~100
things you actually installed**.

## Scan once, filter live

A scan collects the **full enriched dataset once**; the filters are then an
instant in-memory view — no rescanning when you change them.

- **Size tiers (the 3 scans):** `All` · `≥100 MB` · `≥1 GB` (or any exact `--min-size`)
- **Kinds:** Apps · Tools · Libraries
- **Manual only:** hide auto-installed dependencies (on by default)

**Default view:** manually-installed **Apps + CLI Tools**, libraries hidden.

## Quick Start

### Easiest: Zero-Setup Launcher (Unix / Linux / macOS)

The root `./appdetect` script automatically bootstraps a Python virtual environment in `.venv` and installs the package on first run, so you can execute the app immediately with no manual setup:

```bash
# Launch the GUI
./appdetect

# Run CLI commands
./appdetect scan
./appdetect scan -o my_apps.json
```

### Alternative: Manual Installation (All Platforms)

If you prefer a standard virtual environment or need global installation:

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .

# Run CLI commands
app_detector_cli scan

# Launch the GUI
app_detector
```

### Scan

```bash
app_detector_cli scan                       # default: manual apps + tools
app_detector_cli scan --tier large          # only ≥100 MB
app_detector_cli scan --tier huge           # only ≥1 GB
app_detector_cli scan --min-size 250MB      # exact floor
app_detector_cli scan --include-libraries   # add libraries
app_detector_cli scan --all-packages        # include auto-pulled deps (everything)
app_detector_cli scan --kind app            # apps only

app_detector_cli scan -o my_apps.json       # save the filtered view
app_detector_cli scan --full -o full.json   # save the entire dataset (re-filter later)
```

### Restore

Restore is **cross-OS** and **verified**. Each app is resolved to a package
manager the *target* machine actually has (an apt snapshot installs via
`dnf`/`brew`/`winget`), then checked for real presence afterwards — a package
manager that exits 0 without installing can't fake success.

```bash
app_detector_cli restore my_apps.json --dry-run   # preview the resolved commands
app_detector_cli restore my_apps.json             # interactive selection
app_detector_cli restore my_apps.json --auto      # install everything
app_detector_cli restore full.json --tier large   # re-filter a full snapshot
app_detector_cli restore my_apps.json --report failed.json   # save failures to retry
app_detector_cli restore my_apps.json --no-verify --no-config # skip checks/config
```

Apps with no installable manager on this OS are **skipped and listed**, never
silently dropped. The dry-run annotates each line with `(mapped)`/`(guess)` when
the source manager differs from the target.

### Capture & restore app config

Pass `--with-config` to a scan to also snapshot the configuration that's annoying
to redo by hand. Restore replays it automatically (disable with `--no-config`).
Only **safe, idempotent** state is captured — never blind file overwrites.

```bash
app_detector_cli scan --with-config -o my_apps.json
```

| Handler | Captures | Restores via |
|---------|----------|--------------|
| VS Code extensions | `code --list-extensions` | `code --install-extension` |
| Git global config | `git config --global --list` | `git config --global` |

### Fix a misclassification (sticks across scans)

When the App/Tool/Library guess is wrong, correct it once — the override is
re-applied on every future scan.

```bash
app_detector_cli classify docker.io tool      # set
app_detector_cli classify docker.io --clear    # forget
```

### Compare machines — or your snapshot vs. right now

```bash
app_detector_cli diff machine_a.json machine_b.json
app_detector_cli diff my_apps.json --live      # what the snapshot has that I'm missing now
app_detector_cli merge machine_a.json machine_b.json -o combined.json
```

### GUI

```bash
app_detector            # or: python -m app_detector.gui.main
```

Scan once, then drag the size tier / toggle kind checkboxes / flip the
"manually installed only" switch and watch the list and totals update instantly.

## Supported sources

| OS | Sources |
|----|---------|
| Linux | apt/dpkg, dnf/rpm, pacman, snap, flatpak |
| Windows | Registry (uninstall keys), winget, Chocolatey |
| macOS | system_profiler, Homebrew (formulae + casks) |

## Tests

```bash
pip install pytest
python -m pytest app_detector/tests/ -v
```

## License

MIT
