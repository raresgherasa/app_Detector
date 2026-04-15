"""Rich-based logging and progress helpers."""

from __future__ import annotations

from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    TimeRemainingColumn,
)

console = Console()


def get_progress() -> Progress:
    """Return a pre-configured Rich progress bar."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=40),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
    )


def info(msg: str) -> None:
    console.print(f"[bold cyan]ℹ[/]  {msg}")


def success(msg: str) -> None:
    console.print(f"[bold green]✔[/]  {msg}")


def warn(msg: str) -> None:
    console.print(f"[bold yellow]⚠[/]  {msg}")


def error(msg: str) -> None:
    console.print(f"[bold red]✖[/]  {msg}")
