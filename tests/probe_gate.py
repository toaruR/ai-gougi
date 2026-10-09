"""Branch gates derived from .strict-goal/scratch/probe_report.json (written by probe_clis.py)."""
import json
import sys
from pathlib import Path

DEFAULT_REPORT = Path(__file__).resolve().parent.parent / ".strict-goal" / "scratch" / "probe_report.json"
AGY_EXE_LEN_REF = 38


def load_probe_report(path=None):
    p = Path(path) if path else DEFAULT_REPORT
    return json.loads(p.read_text(encoding="utf-8"))


def _rep(report):
    if report is not None:
        return report
    if not DEFAULT_REPORT.exists():  # absent default report -> defaults (live-probe fallback per plan)
        return {}
    return load_probe_report()


def real_kill_enabled(report=None):
    r = _rep(report)
    return sys.platform == "win32" and bool(r.get("taskkill_available"))


def agy_branch(report=None):
    ext = (_rep(report).get("clis", {}).get("agy") or {}).get("ext")
    if ext == ".cmd":
        return "cmd"
    if ext == ".exe":
        return "exe"
    return "unknown"


def authoritative_agy_branches(report=None):
    b = agy_branch(report)
    return ("cmd",) if b == "cmd" else ("exe",) if b == "exe" else ("cmd", "exe")


def agy_exe_len(report=None):
    agy = _rep(report).get("clis", {}).get("agy") or {}
    if agy.get("found") and agy.get("exe_len") is not None:
        return agy["exe_len"]
    return AGY_EXE_LEN_REF
