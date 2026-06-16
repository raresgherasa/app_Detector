# Close the five restore/snapshot gaps — App Detector

The core scan/filter design was solid; the gaps were all on the *restore* and
*correctness* side. Each gap got a small, self-contained module so the existing
architecture (scan once → pure filter → portable manifest) stayed untouched.

## Gaps & solutions

1. **Restore was OS-locked.** A manifest's `source="apt"` only restored on apt.
   - `models.canonical_key()` + `AppEntry.canonical` — OS-agnostic identity.
   - `resolve.py` — curated cross-manager alias table + `exact|mapped|guess`
     resolution against the *target's* available managers; honest `unresolved`.
   - [x] apt/winget snapshots now install via the target's real manager.

2. **No verification.** `install()` trusted the package manager's exit code.
   - `Installer.is_installed()` per platform (cheap presence check).
   - `restore.py` — `plan() → install → verify → RestoreReport`; an install that
     exits 0 but isn't actually present is reported as **failed**.
   - [x] `--report FILE` writes a re-runnable manifest of just the failures.

3. **Snapshots were config-blind.** Captured *that* you have VS Code, not its
   extensions.
   - `config_capture.py` — pluggable `ConfigHandler`s (VS Code extensions, Git
     global config); safe/idempotent only, never file overwrites.
   - `Manifest.configs` field; `scan --with-config` captures, `restore` replays.
   - [x] verified end-to-end on this machine.

4. **No "snapshot vs. now".** `diff` only compared two files.
   - `compare.py` — canonical-keyed set diff; `diff FILE --live` scans the
     current machine (filtered to the default view) and shows missing/extra.
   - [x] self-diff of a fresh snapshot reports 0 missing / 0 extra.

5. **Classification was silent & uncorrectable.**
   - `overrides.py` — persistent `package_id → Kind` in the user config dir,
     re-applied after every scan; `classify` CLI command to set/clear.
   - [x] override survives and re-applies on the next scan.

## GUI wiring (follow-up — done)
The GUI restore path was wired to the same correctness layer, keeping its live
streaming console:
- `_restore_worker` now calls `restore.plan()` to resolve each app cross-manager,
  lists+skips unresolvable apps, stream-installs the *resolved* app (annotating
  `[via <manager>]` when it differs), then verifies with `is_installed()`.
- After installs it replays `manifest.configs` via `config_capture.restore_all`
  (new optional `on_line` callback streams progress into the console).
- `_save_manifest` now captures config via `capture_all()`, so GUI snapshots
  carry the same data as `scan --with-config`.

## Verification
- 54 unit tests pass (28 original + 26 new: resolve, restore, overrides,
  compare, config capture, and the GUI worker — all pure-logic / headless,
  no real subprocess calls).
- CLI smoke-tested live: a Windows winget manifest dry-run-restored on Ubuntu
  mapped Firefox/VS Code → `apt install …` and flagged the unknown vendor app;
  `scan --with-config` captured VS Code + git; `diff --live` and `--report` work.
- GUI worker headless-tested: same winget→apt resolution, skip, verify, and
  config replay, driven through a stub `self.after`.

## Review
- Every gap is a new module the CLI *and* GUI compose; no scanner/filter code
  changed except adding `is_installed()` overrides and the `canonical` field.
- `resolve` and verification are honest about uncertainty (`guess`, `unknown`,
  `unresolved`) rather than pretending — matches the "prove it works" standard.
- The GUI keeps its live-streaming install console (its key UX) while gaining
  cross-manager resolution, verification, and config replay.
