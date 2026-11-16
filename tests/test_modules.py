"""Tests for module logic: discovery, param-audit, sqlmap parsing, OAST helpers."""
import asyncio
from pathlib import Path
from unittest.mock import patch

from vforge.core import runner
from vforge.core.context import Context
from vforge.core.roe import RulesOfEngagement
from vforge.modules import discover
from vforge.modules.base import PHASES
from vforge.modules.webtest import ParamAudit, SqliScan
from vforge.modules.oast import inject, ssrf_candidates, correlate, OastSsrf


def _run(coro):
    return asyncio.run(coro)


def test_all_modules_discover_with_valid_phase():
    mods = discover()
    assert len(mods) >= 12
    for m in mods:
        assert m.phase in PHASES


def test_param_audit_flags_ssrf_and_idor(tmp_path):
    ctx = Context(target="https://app.tld", workdir=tmp_path, profile={},
                  roe=RulesOfEngagement())
    ctx.data["crawled_urls"] = [
        "https://app.tld/fetch?url=x&id=5",
        "https://app.tld/doc?document=7",
        "https://app.tld/static.png",          # no params -> ignored
    ]
    _run(ParamAudit().run(ctx))
    classes = sorted(f.metadata["class"] for f in ctx.findings)
    assert classes == ["IDOR", "IDOR", "SSRF"]


def test_sqlmap_parser_extracts_injection(tmp_path):
    sample = (
        "[INFO] testing URL 'https://app.tld/q?id=1'\n"
        "[INFO] GET parameter 'id' is vulnerable.\n"
        "back-end DBMS: MySQL\n"
    )

    class R:
        stdout = sample
        ok = True
        def lines(self): return [l for l in sample.splitlines() if l.strip()]

    async def fake(cmd, timeout=0, stdin=None):
        return R()

    ctx = Context(target="https://app.tld", workdir=tmp_path, profile={})
    ctx.data["crawled_urls"] = ["https://app.tld/q?id=1"]
    with patch.object(runner, "run", fake):
        _run(SqliScan().run(ctx))
    assert any(f.severity == "high" and "id" in f.title for f in ctx.findings)


def test_sqlmap_csv_parser_is_primary(tmp_path):
    csv = tmp_path / "r.csv"
    csv.write_text(
        'Target URL,Place,Parameter,Technique(s),Note\n'
        '"http://app.tld/q?id=1",GET,id,"boolean-based blind",\n'
    )
    rows = SqliScan._parse_csv(csv)
    assert rows == [{"url": "http://app.tld/q?id=1", "parameter": "id",
                     "place": "GET", "technique": "boolean-based blind"}]
    assert SqliScan._parse_csv(tmp_path / "missing.csv") == []


def test_dalfox_parser_handles_array_and_jsonl():
    from vforge.modules.webtest import XssScan
    arr = '[{"param":"q","data":"p1"}]'
    jsonl = '{"param":"x","data":"p2"}\n{"param":"y","data":"p3"}'
    assert len(XssScan._parse(arr)) == 1
    assert len(XssScan._parse(jsonl)) == 2
    assert XssScan._parse("") == []
    assert XssScan._parse("not json") == []


def test_oast_inject_preserves_other_params():
    out = inject("https://a/f?url=x&id=5", "url", "http://c/")
    assert "id=5" in out and "url=http" in out


def test_oast_candidates_and_correlate():
    roe = RulesOfEngagement()
    cands = ssrf_candidates(["https://a/f?url=x&id=5", "https://a/v?id=1"], roe)
    assert cands == [("https://a/f?url=x&id=5", "url")]

    tag_map = {"vf0": ("u0", "url"), "vf1": ("u1", "next"), "vf10": ("u10", "dest")}
    hits = correlate(['{"full-id":"vf1.c.oast.fun"}'], tag_map)
    assert hits == {"vf1": ("u1", "next")}        # vf1 != vf10


def test_probe_uses_output_not_exit_code(tmp_path):
    # whatweb can exit non-zero (a --log-json flush quirk) yet emit a valid
    # fingerprint; the host must still be recorded live, not silently dropped.
    from vforge.modules.probe import HttpProbe

    json_out = '[{"target":"x","plugins":{"HTTPServer":{},"Python":{}}}]'

    class R:
        returncode = 1
        ok = False
        stdout = json_out
        stderr = "closed stream (IOError)"
        def lines(self): return []

    async def fake(cmd, timeout=0, stdin=None):
        return R()

    ctx = Context(target="http://127.0.0.1:9", workdir=tmp_path, profile={},
                  roe=RulesOfEngagement())
    with patch.object(runner, "run", fake):
        _run(HttpProbe().run(ctx))
    assert any("Live web service" in f.title for f in ctx.findings)
    assert ctx.data["live_urls"] == ["http://127.0.0.1:9"]


def test_whatweb_parser_handles_array_and_empty():
    from vforge.modules.probe import HttpProbe
    # whatweb --log-json emits a JSON array of target objects
    arr = '[\n{"target":"http://x","plugins":{"nginx":{},"PHP":{}}}\n]'
    assert HttpProbe._parse_whatweb(arr) == ["PHP", "nginx"]
    assert HttpProbe._parse_whatweb("[\n]") is None       # no response = not live
    assert HttpProbe._parse_whatweb("") is None
    # older line-delimited fallback still works
    assert HttpProbe._parse_whatweb('{"plugins":{"Apache":{}}}') == ["Apache"]


def test_oast_availability():
    assert not OastSsrf().available()
    assert OastSsrf(options={"payload": "x.oast.fun"}).available()


def test_dalfox_v3_command_and_failed_scan(tmp_path):
    import pytest
    from vforge.core.runner import CommandResult
    from vforge.modules.webtest import XssScan
    commands = []

    async def fake(cmd, timeout=0, stdin=None):
        commands.append(cmd)
        if '--help' in cmd:
            return CommandResult(cmd, 0, 'Commands:\n  scan        Scan targets for XSS\n', '', 0)
        return CommandResult(cmd, 2, '', 'network unreachable', 0)

    ctx = Context(target='http://127.0.0.1/item?id=1', workdir=tmp_path, profile={})
    with patch.object(runner, 'run', fake):
        with pytest.raises(RuntimeError, match='Dalfox scan failed'):
            _run(XssScan().run(ctx))
    assert commands[1][1:4] == ['scan', '--input-type', 'pipe']
    assert '--no-spinner' not in commands[1]
    assert not ctx.findings


def test_dalfox_v2_command_parses_findings(tmp_path):
    from vforge.core.runner import CommandResult
    from vforge.modules.webtest import XssScan
    commands = []

    async def fake(cmd, timeout=0, stdin=None):
        commands.append(cmd)
        if '--help' in cmd:
            return CommandResult(cmd, 0, 'Commands:\n  pipe        Scan stdin\n', '', 0)
        return CommandResult(cmd, 0, '[{"param":"q","url":"http://127.0.0.1/?q=x","data":"test"}]', '', 0)

    ctx = Context(target='http://127.0.0.1/?q=x', workdir=tmp_path, profile={})
    with patch.object(runner, 'run', fake):
        _run(XssScan().run(ctx))
    assert commands[1][1] == 'pipe'
    assert len(ctx.findings) == 1
