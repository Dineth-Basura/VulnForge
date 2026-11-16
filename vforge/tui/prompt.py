"""Interactive prompt layer.

Wraps `questionary` for polished arrow-key selection when it is installed, and
degrades to a clean numbered-menu fallback built on the standard library only —
so the guided UI works on any box even when the optional dependency is absent.

Every helper takes options as ``(value, label)`` pairs and returns the *value*
(or list of values) the operator chose. A Ctrl-C / EOF anywhere raises
``Cancelled`` so callers can return cleanly to the menu instead of crashing.
"""
from __future__ import annotations

from typing import Iterable, Sequence

try:
    import questionary
    from questionary import Choice, Style

    _STYLE = Style([
        ("qmark", "fg:#00afaf bold"),
        ("question", "bold"),
        ("pointer", "fg:#ff5f5f bold"),
        ("highlighted", "fg:#ff5f5f bold"),
        ("selected", "fg:#5fff87"),
        ("answer", "fg:#00afaf bold"),
    ])
    HAVE_QUESTIONARY = True
except Exception:  # questionary not installed
    HAVE_QUESTIONARY = False


class Cancelled(Exception):
    """The operator aborted the prompt (Ctrl-C / EOF)."""


Option = tuple[str, str]  # (value, label)


def _pairs(options: Iterable) -> list[Option]:
    out: list[Option] = []
    for o in options:
        if isinstance(o, (tuple, list)):
            out.append((str(o[0]), str(o[1])))
        else:
            out.append((str(o), str(o)))
    return out


def text(message: str, default: str = "") -> str:
    """Free-text answer. Returns the stripped string (may be empty)."""
    if HAVE_QUESTIONARY:
        ans = questionary.text(message, default=default, style=_STYLE).ask()
        if ans is None:
            raise Cancelled
        return ans.strip()
    try:
        suffix = f" [{default}]" if default else ""
        ans = input(f"  ? {message}{suffix}: ").strip()
    except (KeyboardInterrupt, EOFError):
        raise Cancelled
    return ans or default


def confirm(message: str, default: bool = True) -> bool:
    if HAVE_QUESTIONARY:
        ans = questionary.confirm(message, default=default, style=_STYLE).ask()
        if ans is None:
            raise Cancelled
        return bool(ans)
    hint = "Y/n" if default else "y/N"
    try:
        ans = input(f"  ? {message} ({hint}): ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        raise Cancelled
    if not ans:
        return default
    return ans.startswith("y")


def select(message: str, options: Sequence, default: str | None = None) -> str:
    """Single choice. Returns the chosen value."""
    opts = _pairs(options)
    if HAVE_QUESTIONARY:
        choices = [Choice(title=lbl, value=val) for val, lbl in opts]
        ans = questionary.select(
            message, choices=choices, default=default, style=_STYLE,
            qmark="?", instruction="(↑↓ move, ↵ select)",
        ).ask()
        if ans is None:
            raise Cancelled
        return ans
    print(f"\n  ? {message}")
    for i, (_, lbl) in enumerate(opts, 1):
        marker = "❯" if (default and opts[i - 1][0] == default) else " "
        print(f"   {marker} {i}) {lbl}")
    while True:
        try:
            raw = input("  > ").strip()
        except (KeyboardInterrupt, EOFError):
            raise Cancelled
        if not raw and default is not None:
            return default
        if raw.isdigit() and 1 <= int(raw) <= len(opts):
            return opts[int(raw) - 1][0]
        print("  (enter a number from the list)")


def checkbox(message: str, options: Sequence, checked: Sequence | None = None) -> list[str]:
    """Multi choice. Returns the list of chosen values (possibly empty)."""
    opts = _pairs(options)
    pre = set(checked or [])
    if HAVE_QUESTIONARY:
        choices = [
            Choice(title=lbl, value=val, checked=(val in pre)) for val, lbl in opts
        ]
        ans = questionary.checkbox(
            message, choices=choices, style=_STYLE, qmark="?",
            instruction="(space toggles, ↵ confirm)",
        ).ask()
        if ans is None:
            raise Cancelled
        return list(ans)
    print(f"\n  ? {message}  (comma-separated numbers; blank = the pre-selected set)")
    for i, (val, lbl) in enumerate(opts, 1):
        mark = "x" if val in pre else " "
        print(f"   [{mark}] {i}) {lbl}")
    while True:
        try:
            raw = input("  > ").strip()
        except (KeyboardInterrupt, EOFError):
            raise Cancelled
        if not raw:
            return [v for v, _ in opts if v in pre]
        try:
            picks = {int(x) for x in raw.replace(" ", "").split(",") if x}
        except ValueError:
            print("  (numbers only, e.g. 1,3,4)")
            continue
        if all(1 <= p <= len(opts) for p in picks):
            return [opts[p - 1][0] for p in sorted(picks)]
        print(f"  (numbers must be 1-{len(opts)})")
