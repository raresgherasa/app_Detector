"""Tiny rich-backed logging helpers shared across the package."""

from __future__ import annotations

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn

# Logs/progress go to stderr so stdout stays clean for piped data (e.g. --json-out).
console = Console(stderr=True)


def info(msg: str) -> None:
    console.print(f"[cyan]›[/cyan] {msg}")


def success(msg: str) -> None:
    console.print(f"[green]✓[/green] {msg}")


def warn(msg: str) -> None:
    console.print(f"[yellow]![/yellow] {msg}")


def error(msg: str) -> None:
    console.print(f"[red]✗[/red] {msg}")


def get_progress() -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        console=console,
    )
