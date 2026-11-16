"""Tests for interactive mode: prompt fallback, wizard arg-building, triage wiring.

These exercise the logic without a TTY by scripting the prompt helpers, so they
run head-less in CI regardless of whether `questionary` is installed.
"""
import os

import pytest

from vforge.core.llm import LLMClient
from vforge.tui import prompt, wizard


def _script(monkeypatch, *, texts=(), selects=(), checks=(), confirms=()):
    """Replace the wizard's prompt helpers with scripted, ordered answers."""
    tt, ss, cc, ff = iter(texts), iter(selects), iter(checks), iter(confirms)
    monkeypatch.setattr(wizard.prompt, "text", lambda *a, **k: next(tt))
    monkeypatch.setattr(wizard.prompt, "select", lambda *a, **k: next(ss))
    monkeypatch.setattr(wizard.prompt, "checkbox", lambda *a, **k: next(cc))
    monkeypatch.setattr(wizard.prompt, "confirm", lambda *a, **k: next(ff))


# ---- prompt fallback (force the no-questionary path) ----

def test_prompt_select_fallback_returns_value(monkeypatch):
    monkeypatch.setattr(prompt, "HAVE_QUESTIONARY", False)
    monkeypatch.setattr("builtins.input", lambda *_: "2")
    assert prompt.select("pick", [("a", "Apple"), ("b", "Banana")]) == "b"


def test_prompt_select_fallback_blank_uses_default(monkeypatch):
    monkeypatch.setattr(prompt, "HAVE_QUESTIONARY", False)
    monkeypatch.setattr("builtins.input", lambda *_: "")
    assert prompt.select("pick", [("a", "A"), ("b", "B")], default="b") == "b"


def test_prompt_checkbox_fallback_parses_csv(monkeypatch):
    monkeypatch.setattr(prompt, "HAVE_QUESTIONARY", False)
    monkeypatch.setattr("builtins.input", lambda *_: "1,3")
    got = prompt.checkbox("m", [("x", "x"), ("y", "y"), ("z", "z")])
    assert got == ["x", "z"]


def test_prompt_text_fallback_default(monkeypatch):
    monkeypatch.setattr(prompt, "HAVE_QUESTIONARY", False)
    monkeypatch.setattr("builtins.input", lambda *_: "")
    assert prompt.text("q", default="d") == "d"


# ---- wizard scan assembly ----

def test_build_scan_sets_only_and_enables_intrusive(monkeypatch):
    _script(
        monkeypatch,
        texts=["http://app.tld"],
        selects=["auto"],
        checks=[["http-probe", "sqli-scan"]],   # sqli-scan is intrusive
        confirms=[False, True],                  # no advanced, yes start
    )
    args = wizard._build_scan()
    assert args.target == "http://app.tld"
    assert args.mode == "auto"
    assert args.only == "http-probe,sqli-scan"
    assert args.enable == "sqli-scan"            # intrusive selection auto-enabled


def test_build_scan_requires_target(monkeypatch):
    _script(monkeypatch, texts=[""])
    assert wizard._build_scan() is None


def test_build_scan_aborts_when_not_confirmed(monkeypatch):
    _script(
        monkeypatch,
        texts=["http://app.tld"],
        selects=["manual"],
        checks=[["http-probe"]],
        confirms=[False, False],                 # no advanced, do NOT start
    )
    assert wizard._build_scan() is None


# ---- AI triage wiring ----

def test_configure_triage_sets_env_and_enables_module(monkeypatch):
    for v in ("VULNFORGE_LLM_URL", "VULNFORGE_LLM_MODEL", "VULNFORGE_LLM_KEY"):
        monkeypatch.delenv(v, raising=False)
    _script(
        monkeypatch,
        texts=["llama3.1", "local"],             # model, key
        selects=["http://localhost:11434/v1"],   # endpoint
    )
    args = wizard._args(only="http-probe")
    wizard._configure_triage(args, already_selected=False)
    assert os.environ["VULNFORGE_LLM_URL"] == "http://localhost:11434/v1"
    assert os.environ["VULNFORGE_LLM_MODEL"] == "llama3.1"
    assert os.environ["VULNFORGE_LLM_KEY"] == "local"
    assert "ai-triage" in args.only
    assert "ai-triage" in args.enable


# ---- llm env override feeds the client ----

def test_llm_env_overrides_profile(monkeypatch):
    monkeypatch.setenv("VULNFORGE_LLM_URL", "http://localhost:1234/v1")
    monkeypatch.setenv("VULNFORGE_LLM_MODEL", "mymodel")
    monkeypatch.setenv("VULNFORGE_LLM_KEY", "k")
    profile = {"llm": {"base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"}}
    c = LLMClient.from_profile(profile)
    assert c.base_url == "http://localhost:1234/v1"
    assert c.model == "mymodel"
    assert c.api_key == "k"
