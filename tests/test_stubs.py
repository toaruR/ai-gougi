import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import importlib.util

# site-packages に別の `tests` パッケージがあり `tests.stubs` が解決できないため、パス指定で読み込む。
_spec = importlib.util.spec_from_file_location(
    "make_stubs", Path(__file__).parent / "stubs" / "make_stubs.py")
_ms = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ms)
STUB_CLI, apply_env, install_stubs = _ms.STUB_CLI, _ms.apply_env, _ms.install_stubs


def run(mode, stdin=b"", extra=None, cwd=None, args=()):
    env = dict(os.environ, STUB_MODE=mode, **(extra or {}))
    return subprocess.run([sys.executable, str(STUB_CLI), *args], input=stdin,
                          capture_output=True, env=env, cwd=cwd, timeout=30)


def test_echo_stdin_exit1_sleep():
    data = "全文\nline2".encode("utf-8")
    r = run("echo_stdin", data)
    assert r.returncode == 0 and r.stdout == data
    assert run("exit1").returncode == 1
    t = time.monotonic()
    r = run("sleep", extra={"STUB_SLEEP_SEC": "1"})
    assert r.returncode == 0 and time.monotonic() - t >= 0.9


def test_bytes_ff_record_argv(tmp_path):
    assert b"\xff" in run("bytes_ff").stdout
    f = tmp_path / "argv.json"
    r = run("record_argv", extra={"STUB_ARGV_FILE": str(f)}, args=("-p", "x y"))
    assert r.returncode == 0
    assert json.loads(f.read_text(encoding="utf-8")) == ["-p", "x y"]


def test_make_stubs_resolves_cmd_and_env(tmp_path, monkeypatch):
    env = install_stubs(tmp_path, "echo_stdin")
    assert set(env) == {"AI_GOUGI_BIN_claude", "AI_GOUGI_BIN_codex", "AI_GOUGI_BIN_agy"}
    assert os.path.isabs(env["AI_GOUGI_BIN_claude"])
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])
    w = shutil.which("claude")
    assert w and Path(w).resolve() == Path(env["AI_GOUGI_BIN_claude"]).resolve()
    # agy の .exe 実spawn は python.exe に argv を解釈させられないため、
    # 拡張子による改行規則切替は argv 構築層(test_cmdline)で検証する。
    apply_env(monkeypatch, tmp_path / "b", "echo_stdin")
    assert os.environ["AI_GOUGI_BIN_claude"].endswith("claude.cmd")
    monkeypatch.delenv("STUB_MODE", raising=False)
    r = subprocess.run([env["AI_GOUGI_BIN_codex"]], input=b"hi", capture_output=True, timeout=30)
    assert r.returncode == 0 and r.stdout == b"hi"


def test_print_cwd(tmp_path):
    r = run("print_cwd", cwd=tmp_path)
    assert Path(r.stdout.decode("utf-8")).resolve() == tmp_path.resolve()


def test_exit1_mode_exit_code_1():
    assert run("exit1").returncode == 1
    assert run("no_such_mode").returncode == 2
