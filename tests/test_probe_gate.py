import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests import probe_gate as pg

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / ".strict-goal" / "scratch" / "probe_clis.py"
CLIS = ("claude", "codex", "agy")


def _run(args, force=False):
    env = dict(os.environ)
    env.pop("AI_GOUGI_PROBE_FORCE_MISSING", None)
    if force:
        env["AI_GOUGI_PROBE_FORCE_MISSING"] = "1"
    return subprocess.run([sys.executable, str(SCRIPT), *args], env=env,
                          capture_output=True, text=True, timeout=120)


def _report(taskkill=True, agy_ext=".cmd", exe_len=50):
    clis = {n: {"found": False, "path": None, "ext": None, "exe_len": None, "version": None}
            for n in CLIS}
    if agy_ext is not None:
        clis["agy"] = {"found": True, "path": "C:\\x\\agy" + agy_ext, "ext": agy_ext,
                       "exe_len": exe_len, "version": "1"}
    return {"schema": 1, "platform": "win32", "taskkill_available": taskkill, "clis": clis}


def test_force_missing_all_found_false(tmp_path):
    out, log = tmp_path / "r.json", tmp_path / "l.log"
    r = _run(["--out", str(out), "--log", str(log)], force=True)
    assert r.returncode == 0
    rep = json.loads(out.read_text(encoding="utf-8"))
    for n in CLIS:
        c = rep["clis"][n]
        assert c["found"] is False and c["path"] is None and c["ext"] is None
    assert isinstance(rep["taskkill_available"], bool)


def test_validate_rejects_inconsistent_report(tmp_path):
    rep = _report()
    rep["clis"]["agy"]["path"] = None
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(rep), encoding="utf-8")
    assert _run(["--validate", str(p)]).returncode == 1
    good = tmp_path / "good.json"
    good.write_text(json.dumps(_report()), encoding="utf-8")
    assert _run(["--validate", str(good)]).returncode == 0


def test_log_line_per_cli(tmp_path):
    out, log = tmp_path / "r.json", tmp_path / "l.log"
    assert _run(["--out", str(out), "--log", str(log)], force=True).returncode == 0
    lines = log.read_text(encoding="utf-8").splitlines()
    for n in CLIS:
        assert len([x for x in lines if x.startswith(n + ":") and "found=" in x]) == 1
    _run(["--out", str(out), "--log", str(log)], force=True)
    assert len(log.read_text(encoding="utf-8").splitlines()) == 2 * len(lines)


def test_real_kill_enabled_follows_report(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    assert pg.real_kill_enabled(_report(taskkill=True)) is True
    assert pg.real_kill_enabled(_report(taskkill=False)) is False
    monkeypatch.setattr(sys, "platform", "linux")
    assert pg.real_kill_enabled(_report(taskkill=True)) is False


def test_agy_branch_follows_report():
    assert pg.agy_branch(_report(agy_ext=".cmd")) == "cmd"
    assert pg.authoritative_agy_branches(_report(agy_ext=".cmd")) == ("cmd",)
    assert pg.agy_branch(_report(agy_ext=".exe")) == "exe"
    assert pg.authoritative_agy_branches(_report(agy_ext=".exe")) == ("exe",)
    assert pg.agy_branch(_report(agy_ext=None)) == "unknown"
    assert pg.authoritative_agy_branches(_report(agy_ext=None)) == ("cmd", "exe")


def test_agy_exe_len_from_report():
    assert pg.agy_exe_len(_report(agy_ext=".exe", exe_len=77)) == 77
    assert pg.agy_exe_len(_report(agy_ext=None)) == pg.AGY_EXE_LEN_REF == 38


def test_absent_default_report_uses_defaults(monkeypatch, tmp_path):
    monkeypatch.setattr(pg, "DEFAULT_REPORT", tmp_path / "no_such_report.json")
    assert pg.real_kill_enabled() is False
    assert pg.agy_branch() == "unknown"
    assert pg.authoritative_agy_branches() == ("cmd", "exe")
    assert pg.agy_exe_len() == pg.AGY_EXE_LEN_REF == 38
    with pytest.raises(FileNotFoundError):
        pg.load_probe_report(tmp_path / "explicit_missing.json")
