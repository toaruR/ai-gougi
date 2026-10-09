import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai_gougi.runner import LaunchPlan, prelaunch, run_cli
from ai_gougi.schema import validate_ask_result
from ai_gougi.slots import SlotPool


@pytest.fixture
def bins(tmp_path, monkeypatch):
    out = {}
    for n in ("claude", "codex", "agy"):
        p = tmp_path / f"{n}.cmd"
        p.write_text("@echo off\r\n", encoding="ascii")
        monkeypatch.setenv(f"AI_GOUGI_BIN_{n}", str(p))
        out[n] = str(p)
    return out


def run(coro):
    return asyncio.run(coro)


def code(r):
    assert not isinstance(r, LaunchPlan), r
    validate_ask_result(r)
    return r["error_code"]


def test_input_validation_bounds(bins):
    p = SlotPool(3)
    assert code(run(run_cli("claude", " \n\t", pool=p))) == "INVALID_INPUT"
    assert code(run(run_cli("claude", "", pool=p))) == "INVALID_INPUT"
    assert code(run(run_cli("claude", "a" * 7001, pool=p))) == "PROMPT_TOO_LONG"
    ok = prelaunch("claude", "a" * 7000, pool=p)
    assert isinstance(ok, LaunchPlan)
    assert p.running == 1


@pytest.mark.at("AT-20")
def test_at20_priority_a_to_d(bins, monkeypatch):
    busy = SlotPool(3)
    busy.running = 3
    assert code(prelaunch("codex", "  ", pool=busy)) == "INVALID_INPUT"
    assert code(prelaunch("codex", "a" * 7001, pool=busy)) == "PROMPT_TOO_LONG"
    monkeypatch.setenv("AI_GOUGI_BIN_codex", r"Z:\nope\codex.cmd")
    assert code(prelaunch("codex", "hi", pool=busy)) == "BUSY"
    # (d) agy: BIN 未解決 と CMDLINE 超過 が同時 -> CLI_NOT_FOUND
    monkeypatch.setenv("AI_GOUGI_BIN_agy", r"Z:\nope\agy.cmd")
    free = SlotPool(3)
    assert code(prelaunch("agy", "a" * 7000, pool=free)) == "CLI_NOT_FOUND"
    assert free.running == 0


def test_cli_not_found_message(bins, monkeypatch):
    monkeypatch.setenv("AI_GOUGI_BIN_codex", r"Z:\nope\codex.cmd")
    p = SlotPool(3)
    r = run(run_cli("codex", "hi", pool=p))
    assert r["ok"] is False and r["error_code"] == "CLI_NOT_FOUND"
    assert "BIN_codex" in r["error_message"]
    assert p.running == 0


def test_argv_table(bins):
    p = SlotPool(3)
    c = prelaunch("claude", "hi", pool=p)
    assert c.argv == [bins["claude"], "-p", "--permission-mode", "plan"]
    assert c.stdin_text == "hi" and c.stdin_devnull is False
    x = prelaunch("codex", "hi", pool=p)
    assert x.argv == [bins["codex"], "exec", "--sandbox", "read-only", "--skip-git-repo-check", "-"]
    assert x.stdin_devnull is False
    a = prelaunch("agy", "hi", pool=p)
    assert a.argv == [bins["agy"], "-p", "hi"]
    assert a.stdin_devnull is True and a.stdin_text is None
    # .cmd は改行を \n へ置換
    a2 = prelaunch("agy", "a\nb", pool=SlotPool(3))
    assert a2.argv[2] == "a" + chr(92) + "nb"


def test_agy_cmdline_too_long_releases(bins, monkeypatch):
    monkeypatch.setenv("AI_GOUGI_CMDLINE_MAX_CHARS", "100")
    p = SlotPool(3)
    r = prelaunch("agy", "a" * 200, pool=p)
    assert code(r) == "CMDLINE_TOO_LONG"
    assert p.running == 0
    # claude は stdin 経路なので対象外
    assert isinstance(prelaunch("claude", "a" * 200, pool=p), LaunchPlan)


def test_slot_restored_on_prelaunch_error(bins, monkeypatch):
    p = SlotPool(3)
    p.running = 1
    monkeypatch.setenv("AI_GOUGI_BIN_claude", r"Z:\nope\claude.cmd")
    assert code(run(run_cli("claude", "hi", pool=p))) == "CLI_NOT_FOUND"
    assert p.running == 1
    monkeypatch.setenv("AI_GOUGI_BIN_claude", bins["claude"])
    monkeypatch.setenv("AI_GOUGI_CMDLINE_MAX_CHARS", "50")
    assert code(run(run_cli("agy", "a" * 100, pool=p))) == "CMDLINE_TOO_LONG"
    assert p.running == 1
    # reserved=True は枠に触れない(BUSY でも通過)
    full = SlotPool(3)
    full.running = 3
    assert isinstance(prelaunch("codex", "hi", pool=full, reserved=True), LaunchPlan)
    assert full.running == 3
