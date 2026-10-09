import json
import pytest

from tests import probe_gate
from ai_gougi import cmdline
from ai_gougi.cmdline import (apply_newline, check_cmdline_len, measure_len,
                              n_safe, newline_policy, x_lim)
from ai_gougi.config import base_len, get_config

REF = get_config().AGY_EXE_LEN_REF
EXE = "a" * (REF - 4) + ".exe"
CMD = "a" * (REF - 4) + ".cmd"


def _worst(n0):
    return " " + '"' * (n0 - 1)


def _ok(exe, p):
    try:
        check_cmdline_len(exe, p)
        return True
    except ValueError as e:
        assert "CMDLINE_TOO_LONG" in str(e)
        return False


def test_b_nsafe_xlim():
    assert REF == 38
    assert base_len(REF) == 44
    assert n_safe(REF) == 3978
    assert x_lim(7000, REF) == 956


def test_n_safe_boundary():
    assert measure_len(EXE, _worst(3978)) == 7999
    assert _ok(EXE, _worst(3978))
    assert measure_len(EXE, _worst(3979)) == 8001
    assert not _ok(EXE, _worst(3979))


def test_x_lim_quotes():
    for x, L, ok in ((0, 7044, True), (956, 8000, True), (957, 8001, False)):
        p = " " + "a" * (7000 - 1 - x) + '"' * x
        assert len(p) == 7000
        assert measure_len(EXE, p) == L
        assert _ok(EXE, p) is ok


def test_newline_rule_by_ext():
    assert newline_policy(".cmd") == "escape" and newline_policy(".CMD") == "escape"
    assert newline_policy(".exe") == "keep" and newline_policy(".EXE") == "keep"
    assert apply_newline("a\nb", ".cmd") == "a\\nb"
    assert len(apply_newline("\n", ".cmd")) == 2
    assert apply_newline("a\nb", ".Cmd") == "a\\nb"
    assert apply_newline("a\nb", ".exe") == "a\nb"
    assert apply_newline("a\nb", ".EXE") == "a\nb"


def test_newline_xlim_boundary():
    for x, L in ((956, 8000), (957, 8001)):
        p = " " + "a" * (7000 - 1 - x) + "\n" * x
        assert measure_len(CMD, p) == L
        assert _ok(CMD, p) is (L <= 8000)
    # .exe keeps newlines: no growth
    p = " " + "a" * (7000 - 1 - 957) + "\n" * 957
    assert measure_len(EXE, p) == 44 + 7000


def test_e_measured_not_ref(monkeypatch):
    longexe = "b" * 60 + ".exe"
    p = " " + "a" * (8000 - 44 - 1)  # fits for E=38 (L==8000)
    assert _ok(EXE, p)
    assert not _ok(longexe, p)  # real E=64 -> L==8026, REF not consulted
    # REF override must not affect runtime decision
    monkeypatch.setenv("AI_GOUGI_AGY_EXE_LEN_REF", "1")
    assert measure_len(longexe, p) == 64 + 6 + len(p)
    short = "c.exe"
    assert measure_len(short, p) == 5 + 6 + len(p)
    assert cmdline.resolve_exe_len("definitely-not-a-real-binary-xyz") == len("definitely-not-a-real-binary-xyz")
    # path with space: E measured includes quotes
    assert cmdline.exe_len("C:\\Program Files\\x.exe") == len('"C:\\Program Files\\x.exe"')


def test_check_cmdline_len_raises():
    assert check_cmdline_len(EXE, "a" * 100) is None
    p = " " + "a" * (8000 - 44 - 1)  # L == 8000
    assert measure_len(EXE, p) == 8000
    assert check_cmdline_len(EXE, p) is None
    with pytest.raises(ValueError, match="CMDLINE_TOO_LONG"):
        check_cmdline_len(EXE, p + "a")
    with pytest.raises(ValueError):
        check_cmdline_len("agy.cmd", "a" * 9000)


def _report(ext, exe_len=None):
    if ext is None:
        return {"clis": {"agy": {"found": False, "ext": None, "exe_len": None}}}
    return {"clis": {"agy": {"found": True, "ext": ext, "exe_len": exe_len}}}


def _branch_check(report):
    out = {}
    e = probe_gate.agy_exe_len(report)
    for br in probe_gate.authoritative_agy_branches(report):
        ext = ".cmd" if br == "cmd" else ".exe"
        exe = "a" * (e - 4) + ext
        assert cmdline.exe_len(exe) == e
        out[br] = (newline_policy(ext), apply_newline("x\ny", ext), e)
    return out


def test_gate_agy_branch_from_probe(monkeypatch, tmp_path):
    r = _branch_check(_report(".cmd", 50))
    assert list(r) == ["cmd"] and r["cmd"] == ("escape", "x\\ny", 50)
    r = _branch_check(_report(".exe", 44))
    assert list(r) == ["exe"] and r["exe"] == ("keep", "x\ny", 44)
    r = _branch_check(_report(None))
    assert list(r) == ["cmd", "exe"]
    assert r["cmd"][2] == r["exe"][2] == 38 == probe_gate.AGY_EXE_LEN_REF
    assert r["cmd"][0] == "escape" and r["exe"][0] == "keep"
    # absent default report -> concrete unknown-branch behaviour
    monkeypatch.setattr(probe_gate, "DEFAULT_REPORT", tmp_path / "nonexistent.json")
    assert probe_gate._rep(None) == {}
    assert probe_gate.agy_branch() == "unknown"
    assert probe_gate.authoritative_agy_branches() == ("cmd", "exe")
    assert probe_gate.agy_exe_len() == probe_gate.AGY_EXE_LEN_REF
    r = _branch_check(probe_gate._rep(None))
    assert list(r) == ["cmd", "exe"] and r["cmd"][0] == "escape" and r["exe"][0] == "keep"
    # temp report with each ext selects exactly that branch via the default path
    for ext, br, ln in ((".cmd", "cmd", 50), (".exe", "exe", 44)):
        rp = tmp_path / ("rep%s.json" % ext)
        rp.write_text(json.dumps(_report(ext, ln)), encoding="utf-8")
        monkeypatch.setattr(probe_gate, "DEFAULT_REPORT", rp)
        assert probe_gate.agy_branch() == br
        assert probe_gate.authoritative_agy_branches() == (br,)
        assert probe_gate.agy_exe_len() == ln
        assert list(_branch_check(probe_gate._rep(None))) == [br]
