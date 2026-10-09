import asyncio
import subprocess
import sys
from pathlib import Path

from tests import probe_gate as pg
import pytest

from ai_gougi import killtree
from ai_gougi.killtree import kill_tree, run_taskkill

pytestmark = pytest.mark.at("AT-22")

STUB = Path(__file__).resolve().parent / "stubs" / "grandchild_stub.py"
WIN_ONLY = "win32 only"
win_only = pytest.mark.skipif(sys.platform != "win32", reason=WIN_ONLY)
real_kill = pytest.mark.skipif(not pg.real_kill_enabled(), reason="real kill disabled by probe_report")


def _alive(pid):
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
    return str(pid) in out


async def _spawn_and_kill(monkeypatch, flags):
    monkeypatch.setenv("AI_GOUGI_TASKKILL_FLAGS", flags)
    proc = await asyncio.create_subprocess_exec(
        sys.executable, str(STUB), stdout=asyncio.subprocess.PIPE, stdin=asyncio.subprocess.DEVNULL)
    gc = int((await asyncio.wait_for(proc.stdout.readline(), 15)).decode().strip())
    ok = await kill_tree(proc)
    await asyncio.sleep(1)
    tr = getattr(proc, "_transport", None)
    if tr is not None:
        tr.close()
    return gc, ok


@win_only
@real_kill
def test_kill_tree_removes_grandchild(monkeypatch):
    gc, ok = asyncio.run(_spawn_and_kill(monkeypatch, "/T /F"))
    try:
        assert ok is True
        assert not _alive(gc)
    finally:
        if _alive(gc):
            run_taskkill(gc, "/F")


@win_only
@real_kill
def test_taskkill_f_only_leaves_grandchild(monkeypatch):
    gc, _ = asyncio.run(_spawn_and_kill(monkeypatch, "/F"))
    try:
        assert _alive(gc)
    finally:
        run_taskkill(gc, "/F")


def test_kill_tree_unrecoverable_returns_false(monkeypatch):
    monkeypatch.setenv("AI_GOUGI_KILL_WAIT_SEC", "1")
    monkeypatch.setattr(killtree, "run_taskkill", lambda pid, flags: 0)

    class Stuck:
        pid = 4242

        async def wait(self):
            await asyncio.sleep(60)

    assert asyncio.run(kill_tree(Stuck())) is False


def _skipifs(fn):
    return [m for m in fn.pytestmark if m.name == "skipif"]


def test_win32_only_skip_reason():
    for fn in (test_kill_tree_removes_grandchild, test_taskkill_f_only_leaves_grandchild):
        reasons = [m.kwargs.get("reason", "") for m in _skipifs(fn)]
        assert any("win32 only" in r for r in reasons)
    assert win_only.args[0] == (sys.platform != "win32")
    assert win_only.kwargs["reason"] == WIN_ONLY


def test_marker_at_22(request):
    marks = [m for m in request.node.iter_markers("at")]
    assert marks and marks[0].args == ("AT-22",)
    assert pytestmark.name == "at" and pytestmark.args == ("AT-22",)


def test_kill_tree_builds_taskkill_argv(monkeypatch):
    calls = []

    def fake_run(argv, **kw):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(killtree.subprocess, "run", fake_run)

    class Done:
        pid = 1234

        async def wait(self):
            return 0

    assert asyncio.run(kill_tree(Done())) is True
    assert calls[-1] == ["taskkill", "/PID", "1234", "/T", "/F"]
    monkeypatch.setenv("AI_GOUGI_TASKKILL_FLAGS", "/F")
    asyncio.run(kill_tree(Done()))
    assert calls[-1] == ["taskkill", "/PID", "1234", "/F"]
    assert "/T" not in calls[-1]
    # 実 kill ノードの skip は real_kill_enabled() が False のときだけ
    rk = [m for m in test_kill_tree_removes_grandchild.pytestmark if m.name == "skipif" and m is real_kill.mark]
    assert rk and rk[0].args[0] == (not pg.real_kill_enabled())


def test_run_taskkill_nonexistent_pid_nonzero(monkeypatch):
    assert run_taskkill(99999999, "/T /F") != 0

    def boom(*a, **k):
        raise FileNotFoundError("taskkill")

    monkeypatch.setattr(killtree.subprocess, "run", boom)
    assert run_taskkill(1, "/T /F") != 0

    class P:
        pid = 99999999

        async def wait(self):
            await asyncio.sleep(60)

    monkeypatch.setenv("AI_GOUGI_KILL_WAIT_SEC", "1")
    assert asyncio.run(kill_tree(P())) is False


def _rep(tk):
    return {"taskkill_available": tk, "clis": {}}


def test_gate_real_kill_follows_probe_report():
    assert pg.real_kill_enabled(_rep(True)) == (sys.platform == "win32")
    assert pg.real_kill_enabled(_rep(False)) is False
    live = pg.real_kill_enabled()
    for fn in (test_kill_tree_removes_grandchild, test_taskkill_f_only_leaves_grandchild):
        assert any(m.name == "skipif" and m.args[0] == (not live) for m in fn.pytestmark)
