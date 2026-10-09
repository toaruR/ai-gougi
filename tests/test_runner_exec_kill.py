import asyncio
import pytest
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from ai_gougi.runner import run_cli
from ai_gougi.schema import validate_ask_result
from ai_gougi.slots import SlotPool

_spec = importlib.util.spec_from_file_location(
    "make_stubs", Path(__file__).parent / "stubs" / "make_stubs.py")
_ms = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ms)
apply_env = _ms.apply_env


def go(p="claude", prompt="hello"):
    r = asyncio.run(run_cli(p, prompt, pool=SlotPool(3)))
    validate_ask_result(r)
    return r


def shim(tmp_path, monkeypatch, script: str, name="claude"):
    d = tmp_path / "shim"
    d.mkdir(exist_ok=True)
    (d / "s.py").write_text(script, encoding="utf-8")
    cmd = d / f"{name}.cmd"
    cmd.write_text(f'@echo off\r\n"{sys.executable}" "{d / "s.py"}" %*\r\n', encoding="ascii")
    monkeypatch.setenv(f"AI_GOUGI_BIN_{name}", str(cmd))


@pytest.mark.at("AT-03")
def test_at03_timeout_kill_duration(tmp_path, monkeypatch):
    apply_env(monkeypatch, tmp_path)
    monkeypatch.setenv("STUB_MODE", "sleep")
    monkeypatch.setenv("STUB_SLEEP_SEC", "60")
    monkeypatch.setenv("AI_GOUGI_TIMEOUT_SEC", "3")
    monkeypatch.setenv("AI_GOUGI_KILL_WAIT_SEC", "2")
    r = go()
    assert r["error_code"] == "TIMEOUT" and r["timed_out"] is True and r["ok"] is False
    assert 3000 <= r["duration_ms"] <= 5000, r["duration_ms"]


@pytest.mark.at("AT-14")
def test_at14_utf8_roundtrip_and_replace(tmp_path, monkeypatch, capfd):
    apply_env(monkeypatch, tmp_path)
    monkeypatch.setenv("STUB_MODE", "echo_stdin")
    r = go("claude", "日本語")
    assert r["ok"] is True and r["stdout"] == "日本語"
    monkeypatch.setenv("STUB_MODE", "bytes_ff")
    r = go("claude")
    assert r["ok"] is True and "�" in r["stdout"] and r["stdout"].startswith("ok")
    assert "decode_replaced" in capfd.readouterr().err


def test_partial_output_kept_on_timeout(tmp_path, monkeypatch):
    pidfile = tmp_path / "gc.pid"
    script = (
        "import subprocess,sys,time\n"
        "g=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])\n"
        f"open(r'{pidfile}','w').write(str(g.pid))\n"
        "sys.stdout.write('partial-out');sys.stdout.flush()\n"
        "time.sleep(60)\n"
    )
    shim(tmp_path, monkeypatch, script)
    monkeypatch.setenv("AI_GOUGI_TIMEOUT_SEC", "3")
    monkeypatch.setenv("AI_GOUGI_KILL_WAIT_SEC", "3")
    r = go()
    assert r["timed_out"] is True and r["error_code"] == "TIMEOUT"
    assert "partial-out" in r["stdout"]
    assert r["duration_ms"] <= 3000 + 3000 + 1500
    gpid = int(pidfile.read_text())
    out = subprocess.run(["tasklist", "/FI", f"PID eq {gpid}", "/NH"],
                         capture_output=True, text=True).stdout
    assert str(gpid) not in out


def test_workdir_check_and_truncate_applied(tmp_path, monkeypatch):
    wd = tmp_path / "wd"
    wd.mkdir()
    monkeypatch.setenv("AI_GOUGI_WORKDIR", str(wd))
    monkeypatch.setenv("AI_GOUGI_OUTPUT_MAX_CHARS", "10")
    shim(tmp_path, monkeypatch, "import sys\nsys.stdout.write('x'*50)\n")
    r = go()
    assert r["stdout_truncated"] is True and len(r["stdout"]) == 10
    assert r["stdout_total_chars"] == 50
    assert r["workdir_check"] == "unchanged"
    shim(tmp_path, monkeypatch,
         "import sys\nopen('made.txt','w').write('a')\nsys.stdout.write('hi')\n")
    r = go()
    assert r["workdir_check"] == "changed" and r["ok"] is True


def test_child_env_inherit_plus_extra(tmp_path, monkeypatch):
    monkeypatch.setenv("MY_PARENT_VAR", "inherited")
    monkeypatch.delenv("PYTHONUTF8", raising=False)
    shim(tmp_path, monkeypatch,
         "import os,json,sys\n"
         "sys.stdout.write(json.dumps([os.environ.get('MY_PARENT_VAR'),os.environ.get('PYTHONUTF8')]))\n")
    r = go()
    assert json.loads(r["stdout"]) == ["inherited", "1"]
