"""Guided interactive mode.

Running VulnForge with no sub-command drops you here: a banner, a top-level
menu, and step-by-step prompts that build a scan without memorising a single
flag. It does NOT reimplement scanning — it assembles the same arguments the
CLI uses and hands them to ``cmd_scan``, so both front-ends share one engine.
"""
from __future__ import annotations

import argparse
import os

from vforge.core import tools
from vforge.core.console import banner, good, info, warn
from vforge.modules import discover
from vforge.modules.base import PHASES
from vforge.tui import prompt
from vforge.tui.prompt import Cancelled

# Sensible defaults that mirror the `scan` sub-parser, so the Namespace we build
# is a drop-in for cmd_scan.
_SCAN_DEFAULTS = dict(
    target=None, list=None, concurrency=None, profile=None, output=None,
    only=None, mode="manual", enable=None, header=None, cookie=None,
    proxy=None, notify=None, resume=None, db=None, no_store=False,
)


def _args(**over) -> argparse.Namespace:
    base = dict(_SCAN_DEFAULTS)
    base.update(over)
    return argparse.Namespace(**base)


def run() -> int:
    """Entry point for interactive mode. Returns a process exit code."""
    banner()
    info("Interactive mode — pick an action, or run `vulnforge scan -h` for flags.\n")
    # imported here to avoid a circular import (cli imports nothing from tui at load)
    from vforge.cli import cmd_check, cmd_modules, cmd_scan

    while True:
        try:
            action = prompt.select(
                "What would you like to do?",
                [
                    ("scan", "Run a scan"),
                    ("modules", "List modules & their tool status"),
                    ("check", "Check which external tools are installed"),
                    ("quit", "Quit"),
                ],
                default="scan",
            )
        except Cancelled:
            print()
            info("Bye.")
            return 0

        if action == "quit":
            info("Bye.")
            return 0
        if action == "modules":
            cmd_modules(_args())
            continue
        if action == "check":
            cmd_check(_args())
            continue

        try:
            args = _build_scan()
        except Cancelled:
            print()
            warn("Cancelled — returning to the menu.")
            continue
        if args is None:
            continue

        cmd_scan(args)
        try:
            if not prompt.confirm("Run another task?", default=False):
                info("Reports were saved under the run directory shown above. Bye.")
                return 0
        except Cancelled:
            return 0


def _build_scan() -> argparse.Namespace | None:
    """Walk the operator through a scan; return a ready Namespace or None."""
    target = prompt.text("Target host or URL (e.g. http://testphp.vulnweb.com)")
    if not target:
        warn("A target is required.")
        return None

    mode = prompt.select(
        "Scan mode",
        [
            ("manual", "manual  — recon + probe; intrusive modules opt-in"),
            ("auto", "auto    — full pipeline, bounded by Rules of Engagement"),
        ],
        default="manual",
    )

    mods = sorted(discover(), key=lambda c: (PHASES.index(c.phase), c.name))
    choices, checked = [], []
    for c in mods:
        missing = tools.missing(c.requires)
        tag = " [intrusive]" if c.intrusive else ""
        note = f"  (needs: {', '.join(missing)})" if missing else ""
        choices.append((c.name, f"{c.phase:>8} · {c.name}{tag}{note}"))
        # Pre-check installed, non-intrusive modules (plus all installed in auto);
        # never pre-check ai-triage (it needs an explicit LLM endpoint).
        if not missing and c.name != "ai-triage" and (mode == "auto" or not c.intrusive):
            checked.append(c.name)

    selected = prompt.checkbox("Select modules to run", choices, checked=checked)
    if not selected:
        warn("No modules selected.")
        return None

    args = _args(target=target, mode=mode, only=",".join(selected))
    # Selected intrusive modules must be explicitly enabled to run in manual mode.
    intrusive = [c.name for c in mods if c.intrusive and c.name in selected]
    if intrusive:
        args.enable = ",".join(intrusive)

    if prompt.confirm(
        "Configure advanced settings (profile, auth, proxy, rate, AI triage, notify)?",
        default=False,
    ):
        _advanced(args, "ai-triage" in selected)

    _summary(args)
    if not prompt.confirm("Start scan now?", default=True):
        warn("Not started.")
        return None
    return args


def _advanced(args: argparse.Namespace, triage_selected: bool) -> None:
    profile = prompt.text("Path to a YAML profile (blank = built-in default)")
    if profile:
        args.profile = profile

    output = prompt.text("Output directory (blank = ./runs)")
    if output:
        args.output = output

    cookie = prompt.text("Cookie header value, e.g. 'session=abc' (blank = none)")
    if cookie:
        args.cookie = cookie

    header = prompt.text("Extra header 'Key: Value' (blank = none)")
    if header:
        args.header = [header]

    proxy = prompt.text("Proxy URL, e.g. http://127.0.0.1:8080 (blank = none)")
    if proxy:
        args.proxy = proxy

    notify = prompt.text("Slack/Discord webhook for a finish summary (blank = none)")
    if notify:
        args.notify = notify

    if prompt.confirm(
        "Enable AI triage? (sends finding titles/URLs/evidence to an LLM endpoint)",
        default=False,
    ):
        _configure_triage(args, triage_selected)


def _configure_triage(args: argparse.Namespace, already_selected: bool) -> None:
    """Wire an LLM endpoint via env vars the LLM client reads (no file edits)."""
    info("AI triage uses any OpenAI-compatible endpoint — hosted or a local model.")
    base = prompt.select(
        "LLM endpoint",
        [
            ("http://localhost:11434/v1", "Ollama        (http://localhost:11434/v1)"),
            ("http://localhost:1234/v1", "LM Studio     (http://localhost:1234/v1)"),
            ("https://openrouter.ai/api/v1", "OpenRouter    (https://openrouter.ai/api/v1)"),
            ("custom", "Custom endpoint…"),
        ],
        default="http://localhost:11434/v1",
    )
    if base == "custom":
        base = prompt.text("Base URL (must end in /v1)")
        if not base:
            warn("No endpoint given — skipping AI triage.")
            return
    model = prompt.text("Model name (e.g. llama3.1, gpt-4o-mini)")
    key = prompt.text(
        "API key/token (for local models any non-empty value works, e.g. 'local')"
    )
    if not model or not key:
        warn("Model and key are both required — skipping AI triage.")
        return

    # The LLM client reads these at run time (in-process), so no secret is written
    # to disk and no profile file is modified.
    os.environ["VULNFORGE_LLM_URL"] = base
    os.environ["VULNFORGE_LLM_MODEL"] = model
    os.environ["VULNFORGE_LLM_KEY"] = key

    # Make sure ai-triage actually runs.
    if not already_selected:
        names = [n for n in (args.only or "").split(",") if n]
        if "ai-triage" not in names:
            names.append("ai-triage")
        args.only = ",".join(names)
    enabled = [n for n in (args.enable or "").split(",") if n]
    if "ai-triage" not in enabled:
        enabled.append("ai-triage")
    args.enable = ",".join(enabled)
    good(f"AI triage configured → {base} [model={model}]")


def _summary(args: argparse.Namespace) -> None:
    info("Review:")
    rows = [
        ("target", args.target),
        ("mode", args.mode),
        ("modules", args.only or "all"),
        ("profile", args.profile or "built-in default"),
        ("output", args.output or "runs/"),
        ("proxy", args.proxy or "—"),
        ("auth", "set" if (args.cookie or args.header) else "—"),
        ("notify", "set" if args.notify else "—"),
        ("ai-triage", "on" if (args.enable and "ai-triage" in args.enable) else "off"),
    ]
    for k, v in rows:
        info(f"    {k:<10} {v}")
