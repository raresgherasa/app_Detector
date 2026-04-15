"""CLI interface — scan, restore, diff, merge commands."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from app_detector.core.manifest import Manifest
from app_detector.models.app_entry import AppEntry
from app_detector.utils import logging as log
from app_detector.utils.platform_detect import detect_platform

console = Console()


# ─── Platform factory ──────────────────────────────────────────────────────

def _get_detector():
    info = detect_platform()
    if info.family == "linux":
        from app_detector.platforms.linux import LinuxDetector
        return LinuxDetector(), info
    elif info.family == "windows":
        from app_detector.platforms.windows import WindowsDetector
        return WindowsDetector(), info
    elif info.family == "darwin":
        from app_detector.platforms.macos import MacOSDetector
        return MacOSDetector(), info
    else:
        log.error(f"Unsupported platform: {info.family}")
        sys.exit(1)


def _get_installer():
    info = detect_platform()
    if info.family == "linux":
        from app_detector.platforms.linux import LinuxInstaller
        return LinuxInstaller()
    elif info.family == "windows":
        from app_detector.platforms.windows import WindowsInstaller
        return WindowsInstaller()
    elif info.family == "darwin":
        from app_detector.platforms.macos import MacOSInstaller
        return MacOSInstaller()
    else:
        log.error(f"Unsupported platform: {info.family}")
        sys.exit(1)


# ─── Main CLI group ────────────────────────────────────────────────────────

@click.group()
@click.version_option(package_name="app-detector")
def cli():
    """App Detector — backup & restore your installed applications."""
    pass


# ─── SCAN ──────────────────────────────────────────────────────────────────

@cli.command()
@click.option("-o", "--output", type=click.Path(), default=None,
              help="Export manifest to this file.")
@click.option("--json-out", is_flag=True, help="Print raw JSON to stdout.")
def scan(output: str | None, json_out: bool):
    """Scan the current system for installed applications."""
    detector, info = _get_detector()

    console.print(Panel(
        f"[bold]Platform:[/] {info.distro}\n"
        f"[bold]Managers:[/] {', '.join(info.available_managers) or 'none detected'}",
        title="🔍 App Detector — Scan",
        border_style="cyan",
    ))

    apps = detector.scan()
    manifest = Manifest.create(apps, info)

    if json_out:
        click.echo(manifest.to_json())
        return

    if not apps:
        log.warn("No applications detected.")
        return

    # Show summary table
    _print_app_table(apps, title=f"Detected {len(apps)} applications")

    if output:
        manifest.save(output)
        log.success(f"Manifest saved to [bold]{output}[/bold]")
    else:
        log.info("Tip: use [bold]-o FILE[/bold] to save the manifest.")


# ─── RESTORE ───────────────────────────────────────────────────────────────

@cli.command()
@click.argument("manifest_file", type=click.Path(exists=True))
@click.option("--dry-run", is_flag=True, help="Show commands without executing.")
@click.option("--auto", is_flag=True, help="Install all selected apps without prompting.")
@click.option("--search", default=None, help="Filter apps by name substring.")
def restore(manifest_file: str, dry_run: bool, auto: bool, search: str | None):
    """Restore applications from a manifest file."""
    manifest = Manifest.load(manifest_file)
    info = detect_platform()

    console.print(Panel(
        f"[bold]Manifest:[/] {manifest.summary}\n"
        f"[bold]Target OS:[/] {info.distro}\n"
        f"[bold]Managers:[/] {', '.join(info.available_managers) or 'none detected'}",
        title="📦 App Detector — Restore",
        border_style="green",
    ))

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
        log.warn("Nothing selected for installation.")
        return

    installer = _get_installer()

    if dry_run:
        console.print("\n[bold yellow]DRY RUN — commands that would be executed:[/]\n")
        for app in selected:
            cmd = installer.install_command(app)
            console.print(f"  [dim]$[/] {' '.join(cmd)}")
        return

    # Actual installation
    console.print(f"\n[bold]Installing {len(selected)} applications …[/]\n")
    success_count = 0
    fail_count = 0

    progress = log.get_progress()
    with progress:
        task_id = progress.add_task("Installing …", total=len(selected))
        for app in selected:
            progress.update(task_id, description=f"Installing {app.name}")
            ok = installer.install(app)
            if ok:
                success_count += 1
            else:
                fail_count += 1
            progress.advance(task_id)

    console.print()
    log.success(f"{success_count} installed successfully")
    if fail_count:
        log.error(f"{fail_count} failed to install")


# ─── DIFF ──────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("file1", type=click.Path(exists=True))
@click.argument("file2", type=click.Path(exists=True))
def diff(file1: str, file2: str):
    """Compare two manifest files."""
    m1 = Manifest.load(file1)
    m2 = Manifest.load(file2)

    ids1 = {(a.package_id, a.source) for a in m1.apps}
    ids2 = {(a.package_id, a.source) for a in m2.apps}

    only1 = ids1 - ids2
    only2 = ids2 - ids1
    common = ids1 & ids2

    console.print(Panel(
        f"[bold]Common:[/] {len(common)} apps\n"
        f"[bold]Only in {file1}:[/] {len(only1)} apps\n"
        f"[bold]Only in {file2}:[/] {len(only2)} apps",
        title="📊 Manifest Diff",
        border_style="magenta",
    ))

    if only1:
        console.print(f"\n[bold red]Only in {Path(file1).name}:[/]")
        for pid, src in sorted(only1):
            console.print(f"  • {pid} ({src})")

    if only2:
        console.print(f"\n[bold green]Only in {Path(file2).name}:[/]")
        for pid, src in sorted(only2):
            console.print(f"  • {pid} ({src})")


# ─── MERGE ─────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("file1", type=click.Path(exists=True))
@click.argument("file2", type=click.Path(exists=True))
@click.option("-o", "--output", required=True, type=click.Path(),
              help="Output file for the merged manifest.")
def merge(file1: str, file2: str, output: str):
    """Merge two manifest files into one."""
    m1 = Manifest.load(file1)
    m2 = Manifest.load(file2)
    merged = Manifest.merge(m1, m2)
    merged.save(output)
    log.success(
        f"Merged {len(m1.apps)} + {len(m2.apps)} → {len(merged.apps)} apps → [bold]{output}[/bold]"
    )


# ─── Interactive Selection ─────────────────────────────────────────────────

def _interactive_selection(apps: list[AppEntry]) -> list[AppEntry]:
    """Prompt the user to toggle apps on/off and set version preferences."""
    try:
        from InquirerPy import inquirer
        from InquirerPy.separator import Separator
    except ImportError:
        log.warn("InquirerPy not installed — falling back to select-all mode.")
        return apps

    choices = []
    for app in apps:
        choices.append({
            "name": str(app),
            "value": app.package_id,
            "enabled": app.is_selected,
        })

    selected_ids = inquirer.checkbox(
        message="Select applications to install (SPACE to toggle, ENTER to confirm):",
        choices=choices,
        cycle=True,
        instruction="(↑↓ navigate, SPACE toggle, CTRL+A all, ENTER confirm)",
    ).execute()

    selected_set = set(selected_ids)
    for app in apps:
        app.is_selected = app.package_id in selected_set

    # Version preference
    selected_apps = [a for a in apps if a.is_selected]
    if selected_apps:
        version_choice = inquirer.select(
            message="Version preference for selected apps?",
            choices=[
                {"name": "Install latest versions", "value": "latest"},
                {"name": "Install same versions as before", "value": "same"},
                {"name": "Choose per app", "value": "per-app"},
            ],
        ).execute()

        if version_choice in ("latest", "same"):
            for app in selected_apps:
                app.target_version = version_choice
        else:
            for app in selected_apps:
                choice = inquirer.select(
                    message=f"  {app.name} {app.version}:",
                    choices=[
                        {"name": f"Latest version", "value": "latest"},
                        {"name": f"Same version ({app.version})", "value": "same"},
                    ],
                ).execute()
                app.target_version = choice

    return apps


# ─── Display helpers ───────────────────────────────────────────────────────

def _print_app_table(apps: list[AppEntry], title: str = "Applications"):
    """Pretty-print a table of apps."""
    table = Table(title=title, border_style="blue", show_lines=False)
    table.add_column("#", style="dim", width=5, justify="right")
    table.add_column("Name", style="bold", min_width=20)
    table.add_column("Version", min_width=10)
    table.add_column("Source", style="cyan", min_width=8)
    table.add_column("Description", style="dim", max_width=40)

    for i, app in enumerate(apps[:50], 1):
        desc = app.metadata.get("description", "")[:40]
        table.add_row(str(i), app.name, app.version, app.source, desc)

    if len(apps) > 50:
        table.add_row("…", f"and {len(apps) - 50} more", "", "", "")

    console.print(table)
