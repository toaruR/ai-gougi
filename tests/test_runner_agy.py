"""agy 経路の受入試験(AT-05/12/18/24)。実 CLI は呼ばず .cmd shim を使う。

.cmd の実 spawn は win32 のみ(skip 理由 'win32 only')。argv 構築層の counterpart は全 OS で実行。
"""
import asyncio
import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path

import pytest

from ai_gougi import cmdline, runner
from ai_gougi.config import exe_len, n_safe, x_lim
from ai_gougi.runner import run_cli
from ai_gougi.schema import validate_ask_result
from ai_gougi.slots import SlotPool

_spec = importlib.util.spec_from_file_location(
    "make_stubs", Path(__file__).parent / "stubs" / "make_stubs.py")
_ms = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ms)
apply_env = _ms.apply_env

WIN_ONLY = pytest.mark.skipif(
    sys.platform != "win32", reason="win32 only: agy .cmd real spawn (cmd.exe semantics)")

RECORD = (
    "import json,os,sys\n"
    "with open(os.environ['STUB_ARGV_FILE'],'a',encoding='utf-8') as f:\n"
    "    f.write(json.dumps(sys.argv[1:],ensure_ascii=False)+'\\n')\n"
    "print('ok')\n"
)


def go(prompt):
    r = asyncio.run(run_cli("agy", prompt, pool=SlotPool(3)))
    validate_ask_result(r)
    return r


def _shim(d, body, name="agy"):
    d.mkdir(parents=True, exist_ok=True)
    py = d / f"{name}_s.py"
    py.write_text(body, encoding="utf-8")
    cmd = d / f"{name}.cmd"
    cmd.write_text(f'@echo off\r\n"{sys.executable}" "{py}" %*\r\n', encoding="ascii")
    return cmd


def _setup(tmp_path, monkeypatch, body=RECORD):
    cmd = _shim(tmp_path / "bin", body)
    monkeypatch.setenv("AI_GOUGI_BIN_agy", str(cmd))
    wd = tmp_path / "wd"
    wd.mkdir(exist_ok=True)
    monkeypatch.setenv("AI_GOUGI_WORKDIR", str(wd))
    f = tmp_path / "argv.jsonl"
    monkeypatch.setenv("STUB_ARGV_FILE", str(f))
    e = exe_len(os.path.abspath(shutil.which(str(cmd))))
    return f, wd, e


def _calls(f):
    if not f.exists():
        return []
    return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines()]


@pytest.mark.at("AT-05")
@WIN_ONLY
def test_at05_cmdline_boundary_win32(tmp_path, monkeypatch):
    f, _, e = _setup(tmp_path, monkeypatch)
    n0 = 7000
    xl = x_lim(n0, e)  # E=38 のとき 956
    if e == 38:
        assert xl == 956

    def mk(x):  # 空白1つ(外側引用符を付与させる) + 引用符 x 個、全長 n0
        return " " + "a" * (n0 - 1 - x) + '"' * x

    ok_prompt = mk(xl)
    assert cmdline.measure_len(os.path.abspath(shutil.which(os.environ["AI_GOUGI_BIN_agy"])), ok_prompt) == 8000
    r = go(ok_prompt)
    assert r["ok"] is True, r
    assert _calls(f) == [["-p", ok_prompt]]

    f.unlink()
    r = go(mk(xl + 1))
    assert r["error_code"] == "CMDLINE_TOO_LONG" and r["ok"] is False
    assert _calls(f) == []  # stub 起動0回

    # (b) 最悪形: 空白1 + 引用符のみ。n_safe 個は通り n_safe+1 は拒否
    ns = n_safe(e)
    if e == 38:
        assert ns == 3978
    worst = lambda n: " " + '"' * (n - 1)  # noqa: E731
    r = go(worst(ns))
    assert r["ok"] is True, r
    f.unlink()
    # B が偶数なら ns+1 で L=8001 拒否。B が奇数(tmp パス長依存)だと ns+1 は L=8000 で通り、ns+2 が L=8002 で拒否
    exe_abs = os.path.abspath(shutil.which(os.environ["AI_GOUGI_BIN_agy"]))
    assert cmdline.measure_len(exe_abs, worst(ns)) <= 8000
    l1 = cmdline.measure_len(exe_abs, worst(ns + 1))
    assert l1 in (8000, 8001)
    if e == 38:
        assert l1 == 8001
    nrej = ns + 1 if l1 > 8000 else ns + 2
    if l1 == 8000:
        r = go(worst(ns + 1))
        assert r["ok"] is True, r
        f.unlink()
    r = go(worst(nrej))
    assert r["error_code"] == "CMDLINE_TOO_LONG"
    assert _calls(f) == []


@pytest.mark.at("AT-12")
@WIN_ONLY
def test_at12_workdir_check(tmp_path, monkeypatch):
    mk_body = (
        "import os,sys\n"
        "if os.environ.get('STUB_WRITE')=='1':\n"
        "    open('created.txt','w').write('x')\n"
        "print('ok')\n"
    )
    _, wd, _ = _setup(tmp_path, monkeypatch, mk_body)
    monkeypatch.setenv("STUB_WRITE", "0")
    assert go("hello")["workdir_check"] == "unchanged"
    monkeypatch.setenv("STUB_WRITE", "1")
    r = go("hello")
    assert r["workdir_check"] == "changed" and r["ok"] is True
    assert (wd / "created.txt").exists()

    # 上限超過 -> skipped
    monkeypatch.setenv("STUB_WRITE", "0")
    monkeypatch.setenv("AI_GOUGI_SNAPSHOT_MAX_FILES", "5")
    for i in range(6):
        (wd / f"f{i}.txt").write_text("x")
    assert go("hello")["workdir_check"] == "skipped"

    # cwd == WORKDIR
    monkeypatch.delenv("AI_GOUGI_SNAPSHOT_MAX_FILES")
    monkeypatch.setenv("AI_GOUGI_BIN_agy", apply_env(monkeypatch, tmp_path / "stubs", "print_cwd")["AI_GOUGI_BIN_agy"])
    monkeypatch.setenv("STUB_MODE", "print_cwd")
    r = go("hello")
    assert r["ok"] is True
    assert os.path.normcase(os.path.realpath(r["stdout"].strip())) == os.path.normcase(os.path.realpath(str(wd)))


@pytest.mark.at("AT-18")
@WIN_ONLY
def test_at18_newline_cmd_vs_exe(tmp_path, monkeypatch):
    f, _, _ = _setup(tmp_path, monkeypatch)
    r = go("a\nb")
    assert r["ok"] is True, r
    assert _calls(f) == [["-p", "a\\nb"]]  # リテラル2字 \n
    assert len(_calls(f)[0][1]) == 4

    # .exe 選択時: argv 構築結果は実改行のまま(実 spawn はしない)
    d = tmp_path / "exe"
    d.mkdir()
    exe = d / "agy.exe"
    exe.write_bytes(b"")
    monkeypatch.setenv("AI_GOUGI_BIN_agy", str(exe))
    plan = runner.prelaunch("agy", "a\nb", pool=SlotPool(3))
    assert isinstance(plan, runner.LaunchPlan), plan
    assert plan.argv[1:] == ["-p", "a\nb"]


@pytest.mark.at("AT-24")
@WIN_ONLY
def test_at24_acd(tmp_path, monkeypatch):
    # (a) %CD% は cmd.exe に展開される(not guarded の現状固定)
    f, wd, _ = _setup(tmp_path, monkeypatch)
    r = go("pwd is %CD% ok")
    assert r["ok"] is True, r
    got = _calls(f)[0][1]
    assert "%CD%" not in got
    assert os.path.normcase(os.path.realpath(got.split()[2])) == os.path.normcase(os.path.realpath(str(wd)))

    # (c) agy が作ったファイルは残り changed
    body = "open('left.txt','w').write('x')\nprint('ok')\n"
    _, wd, _ = _setup(tmp_path / "c", monkeypatch, body)
    r = go("hello")
    assert (wd / "left.txt").exists() and r["workdir_check"] == "changed"

    # (d) 認証切れ: NONZERO_EXIT のみ
    body = "import sys\nsys.stderr.write('auth expired\\n')\nsys.exit(1)\n"
    _, _, _ = _setup(tmp_path / "d", monkeypatch, body)
    r = go("hello")
    assert r["error_code"] == "NONZERO_EXIT" and r["exit_code"] == 1 and r["ok"] is False
    assert "auth expired" in r["stderr"]
    assert r["timed_out"] is False


def test_markers_and_skip_reason():
    mod = sys.modules[__name__]
    expect = {
        "test_at05_cmdline_boundary_win32": "AT-05",
        "test_at12_workdir_check": "AT-12",
        "test_at18_newline_cmd_vs_exe": "AT-18",
        "test_at24_acd": "AT-24",
    }
    for name, at in expect.items():
        marks = getattr(getattr(mod, name), "pytestmark", [])
        ats = [m.args[0] for m in marks if m.name == "at"]
        assert ats == [at], (name, marks)
        skips = [m for m in marks if m.name == "skipif"]
        assert skips and "win32 only" in skips[0].kwargs["reason"]
        assert skips[0].args[0] == (sys.platform != "win32")


def test_agy_argv_layer_all_platforms():
    # .cmd: LF -> 2字 \n 置換後の L
    p = "a\nb"
    assert cmdline.newline_policy(".cmd") == "escape"
    assert cmdline.apply_newline(p, ".cmd") == "a\\nb"
    assert cmdline.measure_len("agy.cmd", p) == len('agy.cmd -p a\\nb')
    # .exe: 実改行保持
    assert cmdline.newline_policy(".exe") == "keep"
    assert cmdline.apply_newline(p, ".exe") == "a\nb"
    assert cmdline.measure_len("agy.exe", p) == len(
        __import__("subprocess").list2cmdline(["agy.exe", "-p", "a\nb"]))
    # skip は win32 以外のときだけ
    assert WIN_ONLY.args[0] == (sys.platform != "win32")
