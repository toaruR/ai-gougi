"""deliberate 統合試験B: 時間面(AT-16a/AT-17)。実 run_cli + stub CLI 3者。実 CLI は呼ばない。"""
import asyncio
import sys

import pytest

from ai_gougi.config import get_config, w2
from ai_gougi.deliberate import run_deliberate
from ai_gougi.schema import validate_deliberate_output
from ai_gougi.slots import SlotPool

WIN_ONLY = pytest.mark.skipif(sys.platform != "win32", reason="win32 only: .cmd real spawn")
ORDER = ["claude", "codex", "agy"]

# 受信プロンプト長を記録し、2500字の意見を返す。STUB2_HANG_FROM=N なら N回目以降の呼出しはハング。
STUB_PY = r'''
import os, sys, time
name = sys.argv[1]
d = os.environ["STUB2_DIR"]
if name == "agy":
    a = sys.argv[2:]
    prompt = a[a.index("-p") + 1].replace("\\n", "\n")
else:
    prompt = sys.stdin.buffer.read().decode("utf-8")
f = os.path.join(d, name + ".txt")
with open(f, "a", encoding="utf-8") as fh:
    fh.write(str(len(prompt)) + "\n")
n = len(open(f, encoding="utf-8").read().split())
hang = int(os.environ.get("STUB2_HANG_FROM", "0"))
if hang and n >= hang:
    time.sleep(60)
sys.stdout.buffer.write(("x" * 2500).encode("utf-8"))
'''


def _setup(tmp_path, monkeypatch, hang_from=0, timeout=None, kill_wait=None):
    wd = tmp_path / "wd"
    wd.mkdir(exist_ok=True)
    rec = tmp_path / "rec"
    rec.mkdir(exist_ok=True)
    bins = tmp_path / "bin"
    bins.mkdir(exist_ok=True)
    py = bins / "stub2.py"
    py.write_text(STUB_PY, encoding="utf-8")
    monkeypatch.setenv("AI_GOUGI_WORKDIR", str(wd))
    monkeypatch.setenv("STUB2_DIR", str(rec))
    monkeypatch.setenv("STUB2_HANG_FROM", str(hang_from))
    if timeout is not None:
        monkeypatch.setenv("AI_GOUGI_TIMEOUT_SEC", str(timeout))
    if kill_wait is not None:
        monkeypatch.setenv("AI_GOUGI_KILL_WAIT_SEC", str(kill_wait))
    for name in ORDER:
        p = bins / f"{name}.cmd"
        p.write_text(f'@echo off\r\n"{sys.executable}" "{py}" {name} %*\r\nexit /b %ERRORLEVEL%\r\n',
                     encoding="ascii")
        monkeypatch.setenv(f"AI_GOUGI_BIN_{name}", str(p.resolve()))
    return rec


def go(theme, rounds=2):
    out = asyncio.run(run_deliberate(theme, rounds, pool=SlotPool(3)))
    validate_deliberate_output(out)
    return out


@pytest.mark.at("AT-16")
@WIN_ONLY
def test_at16a_r2_prompt_len_le_w2(tmp_path, monkeypatch):
    rec = _setup(tmp_path, monkeypatch)
    c = get_config()
    out = go("テ" * c.THEME_MAX_CHARS)
    assert out["status"] == "ok" and out["rounds_executed"] == 2
    for name in ORDER:
        lens = [int(x) for x in (rec / f"{name}.txt").read_text().split()]
        assert len(lens) == 2
        assert lens[0] == c.THEME_MAX_CHARS
        r2 = lens[1]
        # 意見は各 2500 字を返しており、2000 字上限まで切詰められて R2 に入る
        assert r2 > c.THEME_MAX_CHARS + 2 * (c.OPINION_MAX_CHARS - c.MARKER_RESERVE)
        assert r2 <= w2() == 6000
        assert r2 <= c.PROMPT_MAX_CHARS == 7000


@pytest.mark.at("AT-17")
@WIN_ONLY
def test_at17a_all_hang_failed_within_tmax1(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, hang_from=1, timeout=3, kill_wait=2)
    out = go("theme hang")
    assert out["status"] == "failed" and out["error_code"] == "ALL_FAILED"
    assert out["rounds_executed"] == 1
    assert all(r["error_code"] == "TIMEOUT" for r in out["rounds"][0]["results"])
    assert out["elapsed_ms"] <= 5000  # T_max(1) = 3 + 2


@pytest.mark.at("AT-17")
@WIN_ONLY
def test_at17b_r2_hang_partial_within_tmax2(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, hang_from=2, timeout=3, kill_wait=2)
    out = go("theme r2 hang")
    assert out["status"] == "partial" and out["rounds_executed"] == 2
    assert all(r["ok"] for r in out["rounds"][0]["results"])
    assert all(r["error_code"] == "TIMEOUT" for r in out["rounds"][1]["results"])
    assert out["elapsed_ms"] <= 10000  # T_max(2) = 2*(3 + 2)
