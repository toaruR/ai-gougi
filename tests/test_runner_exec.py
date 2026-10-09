import asyncio
import pytest
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from ai_gougi import runner
from ai_gougi.runner import run_cli
from ai_gougi.schema import validate_ask_result
from ai_gougi.slots import SlotPool

_spec = importlib.util.spec_from_file_location(
    "make_stubs", Path(__file__).parent / "stubs" / "make_stubs.py")
_ms = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ms)
apply_env = _ms.apply_env

STUB_RUN = Path(__file__).parent / "stubs" / "stub_run.py"


def go(p, prompt="hello", pool=None):
    r = asyncio.run(run_cli(p, prompt, pool=pool or SlotPool(3)))
    validate_ask_result(r)
    return r


@pytest.mark.at("AT-02")
def test_at02_ok_and_empty(tmp_path, monkeypatch):
    apply_env(monkeypatch, tmp_path)
    monkeypatch.setenv("STUB_MODE", "echo_stdin")
    r = go("claude", "hello")
    assert r["ok"] is True and r["stdout"] == "hello" and r["error_code"] is None
    assert r["exit_code"] == 0
    # 空白のみ出力する claude shim
    d = tmp_path / "ws"
    d.mkdir()
    (d / "w.py").write_text("import sys;sys.stdout.write('  \\n\\t ')", encoding="ascii")
    cmd = d / "claude.cmd"
    cmd.write_text(f'@echo off\r\n"{sys.executable}" "{d / "w.py"}"\r\n', encoding="ascii")
    monkeypatch.setenv("AI_GOUGI_BIN_claude", str(cmd))
    r = go("claude", "hello")
    assert r["ok"] is False and r["error_code"] == "EMPTY_OUTPUT" and r["exit_code"] == 0
    # 出力なし exit0 も EMPTY_OUTPUT
    apply_env(monkeypatch, tmp_path)
    monkeypatch.setenv("STUB_MODE", "record_argv")
    assert go("claude")["error_code"] == "EMPTY_OUTPUT"


@pytest.mark.at("AT-15")
def test_at15_stdin_eof_devnull(tmp_path, monkeypatch):
    apply_env(monkeypatch, tmp_path)
    monkeypatch.setenv("STUB_MODE", "echo_stdin")
    text = "全文 line1\nline2"
    for p in ("claude", "codex"):
        r = go(p, text)
        assert r["ok"] is True and r["stdout"] == text, p
    # agy: stdin は DEVNULL(即EOF・空)。echo_stdin は空を返し、ハングせず EMPTY_OUTPUT
    r = go("agy", "hi")
    assert r["exit_code"] == 0 and r["stdout"] == "" and r["error_code"] == "EMPTY_OUTPUT"


@pytest.mark.at("AT-23")
def test_at23_plan_flags_argv(tmp_path, monkeypatch):
    apply_env(monkeypatch, tmp_path)
    monkeypatch.setenv("STUB_MODE", "record_argv")
    f = tmp_path / "argv.json"
    monkeypatch.setenv("STUB_ARGV_FILE", str(f))
    go("claude")
    assert json.loads(f.read_text(encoding="utf-8")) == ["-p", "--permission-mode", "plan"]
    go("codex")
    assert json.loads(f.read_text(encoding="utf-8")) == [
        "exec", "--sandbox", "read-only", "--skip-git-repo-check", "-"]


def test_nonzero_and_spawn_failed(tmp_path, monkeypatch):
    apply_env(monkeypatch, tmp_path)
    monkeypatch.setenv("STUB_MODE", "exit1")
    r = go("claude")
    assert r["ok"] is False and r["error_code"] == "NONZERO_EXIT" and r["exit_code"] == 1
    assert "stub failure" in r["stderr"]

    async def boom(*a, **k):
        raise FileNotFoundError(2, "No such file xyz")

    monkeypatch.setattr(runner.asyncio, "create_subprocess_exec", boom)
    r = go("claude")
    assert r["ok"] is False and r["error_code"] == "SPAWN_FAILED"
    assert r["exit_code"] is None and "No such file xyz" in r["error_message"]


def test_slot_released_all_paths(tmp_path, monkeypatch):
    apply_env(monkeypatch, tmp_path)
    pool = SlotPool(3)
    for mode in ("echo_stdin", "exit1", "record_argv"):
        monkeypatch.setenv("STUB_MODE", mode)
        go("claude", pool=pool)
        assert pool.running == 0
    go("claude", " ", pool=pool)
    assert pool.running == 0

    async def boom(*a, **k):
        raise OSError("nope")

    monkeypatch.setattr(runner.asyncio, "create_subprocess_exec", boom)
    go("claude", pool=pool)
    assert pool.running == 0


def _stub_run(*args):
    return subprocess.run([sys.executable, str(STUB_RUN), *args], capture_output=True,
                          timeout=60, cwd=str(Path(__file__).parent.parent))


def test_stub_run_cli_exit_codes():
    a = _stub_run("claude", "echo_stdin")
    assert a.returncode == 0
    assert json.loads(a.stdout.decode("utf-8"))["ok"] is True
    b = _stub_run("claude", "exit1")
    assert b.returncode == 1
    assert json.loads(b.stdout.decode("utf-8"))["error_code"] == "NONZERO_EXIT"
    assert len(b.stdout.decode("utf-8").strip().splitlines()) == 1
