"""Command-line interface — scan / restore / diff / merge.

Mental model: a scan produces the *full* enriched dataset once; flags build a
:class:`ScanFilter` that is a live view over it. The three size "scans" are
``--tier all|large|huge`` (or a precise ``--min-size 250MB``).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from app_detector import compare as compare_mod
from app_detector import config_capture, overrides, restore as restore_mod
from app_detector.filtering import apply_filter, total_size
from app_detector.manifest import Manifest
from app_detector.models import AppEntry, Kind, ScanFilter, SizeTier, human_size
from app_detector.platform_detect import detect_platform
from app_detector.scanners import get_installer, get_scanner
from app_detector.util import log

console = Console()

_SIZE_RE = re.compile(r"^\s*([\d.]+)\s*([KMGT]?B?)\s*$", re.IGNORECASE)
_UNITS = {"": 1, "B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}


def _parse_size(text: str) -> int:
    """Parse ``250MB`` / ``1.5gb`` / ``1073741824`` → bytes."""
    m = _SIZE_RE.match(text)
    if not m:
        raise click.BadParameter(f"Cannot parse size: {text!r} (try '100MB', '1GB')")
    num, unit = m.groups()
    unit = unit.upper()
    if unit and not unit.endswith("B"):
        unit += "B"
    return int(float(num) * _UNITS.get(unit, 1))


def _parse_kinds(values: tuple[str, ...]) -> set[Kind]:
    kinds: set[Kind] = set()
    for v in values:
        for part in v.split(","):
            part = part.strip().lower()
            if not part:
                continue
            try:
                kinds.add(Kind(part))
            except ValueError:
                raise click.BadParameter(
                    f"Unknown kind {part!r}; choose from: app, tool, library")
    return kinds


def _build_filter(tier: str, min_size: str | None, kind: tuple[str, ...],
                  include_libraries: bool, all_packages: bool) -> ScanFilter:
    kinds = _parse_kinds(kind) if kind else {Kind.APP, Kind.TOOL}
    if include_libraries:
        kinds.add(Kind.LIBRARY)
    min_bytes = _parse_size(min_size) if min_size else SizeTier.from_name(tier).value
    return ScanFilter(min_size_bytes=min_bytes, kinds=kinds,
                      manual_only=not all_packages)


# Shared filter options for scan & restore.
def filter_options(fn):
    fn = click.option("--tier", type=click.Choice(["all", "large", "huge"]),
                      default="all", show_default=True,
                      help="Size tier: all / large (≥100MB) / huge (≥1GB).")(fn)
    fn = click.option("--min-size", default=None,
                      help="Exact size floor, e.g. '250MB' (overrides --tier).")(fn)
    fn = click.option("--kind", multiple=True,
                      help="Kinds to include: app, tool, library (repeatable).")(fn)
    fn = click.option("--include-libraries", is_flag=True,
                      help="Also include libraries/dependencies.")(fn)
    fn = click.option("--all-packages", is_flag=True,
                      help="Include auto-installed deps (disable manual-only).")(fn)
    return fn


@click.group()
@click.version_option(package_name="app-detector")
def cli():
    """App Detector — size & kind aware backup/restore of installed apps."""


# ─── SCAN ────────────────────────────────────────────────────────────────────

@cli.command()
@filter_options
@click.option("-o", "--output", type=click.Path(), default=None,
              help="Save manifest to this file.")
@click.option("--full", is_flag=True,
              help="Save the entire scanned dataset (not just the filtered view).")
@click.option("--with-config", is_flag=True,
              help="Also capture app config (VS Code extensions, git config).")
@click.option("--json-out", is_flag=True, help="Print manifest JSON to stdout.")
def scan(tier, min_size, kind, include_libraries, all_packages,
         output, full, with_config, json_out):
    """Scan the system, then show a filtered view (size + kind aware)."""
    flt = _build_filter(tier, min_size, kind, include_libraries, all_packages)
    scanner = get_scanner()
    info = detect_platform()

    if not json_out:
        console.print(Panel(
            f"[bold]Platform:[/] {info.distro}\n"
            f"[bold]Managers:[/] {', '.join(info.available_managers) or 'none'}",
            title="🔍 Scan", border_style="cyan"))

    all_apps = scanner.scan_all()
    overrides.apply(all_apps)            # honour user Kind corrections
    view = apply_filter(all_apps, flt)

    configs = config_capture.capture_all() if with_config else None
    saved = all_apps if full else view
    manifest = Manifest.create(saved, info, flt.to_dict(), configs)

    if json_out:
        click.echo(manifest.to_json())
        return

    if not all_apps:
        log.warn("No packages detected.")
        return

    _print_table(view, scanned=len(all_apps))

    if output:
        manifest.save(output)
        log.success(
            f"Saved {len(saved)} apps ({'full set' if full else 'filtered view'}) "
            f"→ [bold]{output}[/bold]")
    else:
        log.info("Tip: add [bold]-o FILE[/bold] to save a manifest.")


# ─── RESTORE ─────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("manifest_file", type=click.Path(exists=True))
@filter_options
@click.option("--dry-run", is_flag=True, help="Show commands without executing.")
@click.option("--auto", is_flag=True, help="Install everything without prompting.")
@click.option("--search", default=None, help="Filter apps by name substring.")
@click.option("--no-verify", is_flag=True,
              help="Skip the post-install presence check.")
@click.option("--no-config", is_flag=True,
              help="Don't replay captured app config from the manifest.")
@click.option("--report", "report_path", type=click.Path(), default=None,
              help="Write a re-runnable manifest of failures to this file.")
def restore(manifest_file, tier, min_size, kind, include_libraries, all_packages,
            dry_run, auto, search, no_verify, no_config, report_path):
    """Restore applications from a manifest file."""
    manifest = Manifest.load(manifest_file)
    info = detect_platform()

    console.print(Panel(
        f"[bold]Manifest:[/] {manifest.summary}\n"
        f"[bold]Target OS:[/] {info.distro}",
        title="📦 Restore", border_style="green"))

    # If the manifest holds a full dataset, the same filter flags narrow it.
    flt = _build_filter(tier, min_size, kind, include_libraries, all_packages)
    apps = apply_filter(manifest.apps, flt) if manifest.apps else []
    # Fall back to the raw list if filtering removed everything (curated manifest).
    if not apps and manifest.apps:
        apps = manifest.apps

    if search:
        apps = [a for a in apps if search.lower() in a.name.lower()]
        log.info(f"Filtered to {len(apps)} apps matching '{search}'")

    if not apps:
        log.warn("No apps to restore.")
        return

    if not auto:
        apps = _interactive_selection(apps)

    selected = [a for a in apps if a.is_selected]
    if not selected:
        log.warn("Nothing selected.")
        return

    installer = get_installer()

    # Resolve each app to a manager the *target* machine actually has, so a
    # snapshot taken on another OS still installs (apt → dnf/brew/winget).
    resolvable, unresolved = restore_mod.plan(selected, info)
    if unresolved:
        log.warn(f"{len(unresolved)} app(s) have no installer on this OS — skipped:")
        for a in unresolved:
            console.print(f"  [dim]·[/] {a.name} ({a.source})")

    if dry_run:
        console.print("\n[bold yellow]DRY RUN — commands that would run:[/]\n")
        for _orig, resolved, confidence in resolvable:
            tag = "" if confidence == "exact" else f"  [dim]({confidence})[/]"
            console.print(
                f"  [dim]$[/] {' '.join(installer.install_command(resolved))}{tag}")
        return

    if not resolvable:
        log.warn("Nothing installable on this OS.")
        return

    console.print(f"\n[bold]Installing {len(resolvable)} applications …[/]\n")
    progress = log.get_progress()
    with progress:
        task = progress.add_task("Installing …", total=len(resolvable))

        def _event(stage: str, app: AppEntry) -> None:
            if stage == "installing":
                progress.update(task, description=f"Installing {app.name}")
            else:
                progress.advance(task)

        report = restore_mod.run(installer, selected, info,
                                 on_event=_event, verify=not no_verify)

    _print_restore_report(report)

    # Replay captured app config (extensions, git, …) once apps are present.
    if manifest.configs and not no_config:
        config_capture.restore_all(manifest.configs)

    if report_path and report.failed:
        failed_apps = [r.original for r in report.failed]
        Manifest.create(failed_apps, info).save(report_path)
        log.info(f"Wrote {len(failed_apps)} failures → [bold]{report_path}[/] "
                 f"(retry with: restore {report_path})")


# ─── DIFF / MERGE ────────────────────────────────────────────────────────────

@cli.command()
@click.argument("file1", type=click.Path(exists=True))
@click.argument("file2", required=False, type=click.Path(exists=True))
@click.option("--live", is_flag=True,
              help="Compare FILE1 against the apps installed right now.")
def diff(file1, file2, live):
    """Compare two manifests, or a manifest against the live machine (--live).

    With ``--live`` the most useful question during a restore is answered:
    *what does this snapshot have that I'm missing right now?*
    """
    if live == bool(file2):
        raise click.UsageError("Pass two files, or one file with --live (not both).")

    m1 = Manifest.load(file1)
    if live:
        scanner = get_scanner()
        # Match the live machine to the default snapshot view (manual apps +
        # tools) so "extra here" is meaningful, not 2800 system libraries.
        live_apps = apply_filter(scanner.scan_all(), ScanFilter())
        label1, label2 = Path(file1).name, "this machine"
        cmp = compare_mod.compare(m1.apps, live_apps)
    else:
        m2 = Manifest.load(file2)
        label1, label2 = Path(file1).name, Path(file2).name
        cmp = compare_mod.compare(m1.apps, m2.apps)

    console.print(Panel(
        f"[bold]Common:[/] {len(cmp.common)}\n"
        f"[bold]Only in {label1}:[/] {len(cmp.only_a)}"
        + ("  [dim](missing here)[/]" if live else "") + "\n"
        f"[bold]Only in {label2}:[/] {len(cmp.only_b)}"
        + ("  [dim](extra here)[/]" if live else ""),
        title="📊 Diff", border_style="magenta"))
    for lbl, apps, colour in ((label1, cmp.only_a, "red"),
                              (label2, cmp.only_b, "green")):
        if apps:
            console.print(f"\n[bold {colour}]Only in {lbl}:[/]")
            for a in sorted(apps, key=lambda x: x.name.lower()):
                console.print(f"  • {a.name} [dim]({a.source})[/]")


@cli.command()
@click.argument("file1", type=click.Path(exists=True))
@click.argument("file2", type=click.Path(exists=True))
@click.option("-o", "--output", required=True, type=click.Path())
def merge(file1, file2, output):
    """Merge two manifest files into one."""
    m1, m2 = Manifest.load(file1), Manifest.load(file2)
    merged = Manifest.merge(m1, m2)
    merged.save(output)
    log.success(f"Merged {len(m1.apps)} + {len(m2.apps)} → "
                f"{len(merged.apps)} apps → [bold]{output}[/bold]")


# ─── CLASSIFY (overrides) ──────────────────────────────────────────────────────

@cli.command()
@click.argument("package_id")
@click.argument("kind", required=False,
                type=click.Choice(["app", "tool", "library"]))
@click.option("--clear", "do_clear", is_flag=True,
              help="Remove the override for PACKAGE_ID instead of setting it.")
def classify(package_id, kind, do_clear):
    """Override the App/Tool/Library guess for a package (sticks across scans).

    \b
    app_detector_cli classify docker.io tool     # fix a misclassified package
    app_detector_cli classify docker.io --clear   # forget the override
    """
    if do_clear:
        removed = overrides.clear(package_id)
        log.success(f"Cleared override for {package_id}") if removed else \
            log.warn(f"No override set for {package_id}")
        return
    if not kind:
        raise click.UsageError("Provide a KIND (app|tool|library) or use --clear.")
    overrides.set_kind(package_id, Kind(kind))
    log.success(f"{package_id} → {kind} (applied on every future scan)")


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _print_restore_report(report: "restore_mod.RestoreReport") -> None:
    """Summarise a restore: verified OK / failed, with the failure reasons."""
    ok, failed = report.ok, report.failed
    log.success(f"{len(ok)} installed & verified") if ok else None
    mapped = [r for r in ok if r.confidence != "exact"]
    if mapped:
        log.info(f"{len(mapped)} installed via a different manager than the source.")
    if failed:
        log.error(f"{len(failed)} failed:")
        for r in failed:
            why = ("install command failed" if not r.installed
                   else "installed but not detected afterwards")
            console.print(f"  [red]✗[/] {r.resolved.name} "
                          f"[dim]({r.resolved.source}: {why})[/]")

def _print_table(apps: list[AppEntry], scanned: int) -> None:
    table = Table(title=f"Showing {len(apps)} of {scanned} scanned · "
                        f"{human_size(total_size(apps))}",
                  border_style="blue")
    table.add_column("#", style="dim", justify="right", width=4)
    table.add_column("Name", style="bold", min_width=20)
    table.add_column("Version", min_width=8)
    table.add_column("Size", justify="right")
    table.add_column("Kind", style="cyan")
    table.add_column("Source", style="dim")

    for i, app in enumerate(apps[:60], 1):
        table.add_row(str(i), app.name, app.version, app.size_human,
                      app.kind.value, app.source)
    if len(apps) > 60:
        table.add_row("…", f"and {len(apps) - 60} more", "", "", "", "")
    console.print(table)


def _interactive_selection(apps: list[AppEntry]) -> list[AppEntry]:
    try:
        from InquirerPy import inquirer
    except ImportError:
        log.warn("InquirerPy not installed — selecting all.")
        return apps

    choices = [{"name": str(a), "value": a.package_id, "enabled": a.is_selected}
               for a in apps]
    selected_ids = set(inquirer.checkbox(
        message="Select apps to install (SPACE toggle, ENTER confirm):",
        choices=choices, cycle=True,
        instruction="(↑↓ navigate · SPACE toggle · CTRL+A all · ENTER confirm)",
    ).execute())
    for a in apps:
        a.is_selected = a.package_id in selected_ids

    selected = [a for a in apps if a.is_selected]
    if selected:
        pref = inquirer.select(
            message="Version preference?",
            choices=[{"name": "Latest versions", "value": "latest"},
                     {"name": "Same versions as before", "value": "same"}],
        ).execute()
        for a in selected:
            a.target_version = pref
    return apps
