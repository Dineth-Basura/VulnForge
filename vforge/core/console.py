"""Thin console layer. Uses `rich` when available, degrades to plain print."""
from __future__ import annotations

try:
    from rich.console import Console as _RichConsole

    _console = _RichConsole()

    def _emit(markup: str) -> None:
        _console.print(markup)

    HAVE_RICH = True
except Exception:  # rich not installed
    HAVE_RICH = False

    def _emit(markup: str) -> None:
        # strip the simplest rich tags for a clean plain fallback
        import re

        print(re.sub(r"\[/?[a-z0-9 _#]+\]", "", markup))


_ICONS = {
    "info": "[bold cyan][*][/bold cyan]",
    "good": "[bold green][+][/bold green]",
    "warn": "[bold yellow][!][/bold yellow]",
    "bad": "[bold red][-][/bold red]",
    "phase": "[bold magenta][>][/bold magenta]",
}


def info(msg: str) -> None:
    _emit(f"{_ICONS['info']} {msg}")


def good(msg: str) -> None:
    _emit(f"{_ICONS['good']} {msg}")


def warn(msg: str) -> None:
    _emit(f"{_ICONS['warn']} {msg}")


def bad(msg: str) -> None:
    _emit(f"{_ICONS['bad']} {msg}")


def phase(msg: str) -> None:
    _emit(f"{_ICONS['phase']} [bold]{msg}[/bold]")


def banner() -> None:
    from vforge import __version__

    _emit(
        "[bold red]\n"
        "  V U L N F O R G E\n"
        "[/bold red]"
        f"[dim]  Automated Web Pentesting Framework v{__version__}[/dim]\n"
        "[bold cyan]  Created by dineth[/bold cyan]\n"
    )
