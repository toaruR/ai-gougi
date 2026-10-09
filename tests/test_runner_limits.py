import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

from ai_gougi import runner
from ai_gougi.runner import run_cli
from ai_gougi.schema import validate_ask_result
from ai_gougi.slots import SlotPool

_spec = importlib.util.spec_from_file_location(
    "make_stubs", Path(__file__).parent / "stubs" / "make_stubs.py")
_ms = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ms)
apply_env = _ms.apply_env


def go(p, prompt="hello"):
    r = asyncio.run(run_cli(p, prompt, pool=SlotPool(3)))
    validate_ask_result(r)
    return r


def _shim(d, script_body, name="claude"):
    d.mkdir(parents=True, exist_ok=True)
    py = d / f"{name}_s.py"
    py.write_text(script_body, encoding="utf-8")
    cmd = d / f"{name}.cmd"
    cmd.write_text(f'@echo off\r\n"{sys.executable}" "{py}" %*\r\n', encoding="ascii")
    return cmd


@pytest.mark.at("AT-04")
def test_at04_prompt_boundary(tmp_path, monkeypatch):
    apply_env(monkeypatch, tmp_path)
    f = tmp_path / "argv.json"
    monkeypatch.setenv("STUB_MODE", "record_argv")
    monkeypatch.setenv("STUB_ARGV_FILE", str(f))
    r = go("claude", "a" * 7001)
    assert r["error_code"] == "PROMPT_TOO_LONG" and r["ok"] is False
    assert not f.exists()  # stub 起動回数0
    r = go("claude", "a" * 7000)
    assert r["error_code"] != "PROMPT_TOO_LONG"
    assert f.exists()  # 7000 字は受理され stub 起動
    monkeypatch.setenv("STUB_MODE", "echo_stdin")
    r = go("claude", "a" * 7000)
    assert r["ok"] is True and r["stdout"] == "a" * 7000


def test_at06_output_stderr_truncation(tmp_path, monkeypatch):
    body = (
        "import os,sys\n"
        "n=int(os.environ['STUB_OUT_N']); m=int(os.environ['STUB_ERR_N'])\n"
        "sys.stdout.buffer.write(b'x'*n)\n"
        "sys.stderr.buffer.write(b'a'*(m-4000)+b'e'*4000 if m>=4000 else b'e'*m)\n"
    )
    monkeypatch.setenv("AI_GOUGI_BIN_claude", str(_shim(tmp_path, body)))
    monkeypatch.setenv("STUB_OUT_N", "20000")
    monkeypatch.setenv("STUB_ERR_N", "10")
    r = go("claude")
    assert r["stdout"] == "x" * 20000 and r["stdout_truncated"] is False
    assert r["stdout_total_chars"] == 20000

    monkeypatch.setenv("STUB_OUT_N", "20001")
    monkeypatch.setenv("STUB_ERR_N", "4001")
    r = go("claude")
    assert r["stdout_truncated"] is True and r["stdout_total_chars"] == 20001
    assert r["stdout"].startswith("x" * 20000)
    assert r["stderr_truncated"] is True and r["stderr_total_chars"] == 4001
    assert "e" * 4000 in r["stderr"] and r["stderr"].endswith("e" * 4000)
    assert "a" not in r["stderr"].replace("…", "").split("e" * 4000)[-1]


@pytest.mark.at("AT-20")
def test_at20ef_priority(tmp_path, monkeypatch):
    apply_env(monkeypatch, tmp_path)
    # (e) timeout + 非0終了(kill により非0)
    monkeypatch.setenv("STUB_MODE", "sleep")
    monkeypatch.setenv("STUB_SLEEP_SEC", "30")
    monkeypatch.setenv("AI_GOUGI_TIMEOUT_SEC", "1")
    r = go("claude")
    assert r["timed_out"] is True and r["error_code"] == "TIMEOUT" and r["ok"] is False
    assert r["exit_code"] != 0
    # (f) 非0終了 + 空 stdout
    monkeypatch.delenv("AI_GOUGI_TIMEOUT_SEC")
    monkeypatch.setenv("STUB_MODE", "exit1")
    r = go("claude")
    assert r["stdout"] == "" and r["exit_code"] == 1
    assert r["error_code"] == "NONZERO_EXIT" and r["timed_out"] is False


@pytest.mark.skipif(sys.platform != "win32", reason="Windows code page mojibake")
@pytest.mark.at("AT-21")
def test_at21_pythonutf8_win32(tmp_path, monkeypatch):
    body = "print('日本語')\n"
    monkeypatch.setenv("AI_GOUGI_BIN_claude", str(_shim(tmp_path, body)))
    monkeypatch.delenv("PYTHONUTF8", raising=False)
    monkeypatch.delenv("PYTHONIOENCODING", raising=False)
    monkeypatch.delenv("AI_GOUGI_CHILD_ENV_EXTRA", raising=False)
    r = go("claude")
    assert r["stdout"].strip() == "日本語"
    monkeypatch.setenv("AI_GOUGI_CHILD_ENV_EXTRA", "")
    r = go("claude")
    assert r["stdout"].strip() != "日本語"


def test_child_env_construction(tmp_path, monkeypatch):
    apply_env(monkeypatch, tmp_path)
    monkeypatch.delenv("PYTHONUTF8", raising=False)
    seen = {}

    async def fake(*a, **k):
        seen["env"] = k["env"]
        raise OSError("captured")

    monkeypatch.setattr(runner.asyncio, "create_subprocess_exec", fake)
    monkeypatch.delenv("AI_GOUGI_CHILD_ENV_EXTRA", raising=False)
    go("claude")
    assert seen["env"].get("PYTHONUTF8") == "1"
    seen.clear()
    monkeypatch.setenv("AI_GOUGI_CHILD_ENV_EXTRA", "")
    go("claude")
    assert "PYTHONUTF8" not in seen["env"]
