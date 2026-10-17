import os
import subprocess
import sys

import pytest

from ai_gougi.config import get_config, keep, marker_len, n_safe, return_cap, t_max, w2, x_lim


def test_defaults_match_table():
    c = get_config()
    assert (c.TIMEOUT_SEC, c.KILL_WAIT_SEC) == (600, 5)
    assert (c.AGY_EMPTY_OUTPUT_RETRIES, c.AGY_RETRY_DELAY_SEC) == (2, 1)
    assert (c.PROMPT_MAX_CHARS, c.CMDLINE_MAX_CHARS, c.AGY_EXE_LEN_REF) == (7000, 8000, 38)
    assert (c.CMDLINE_FIXED_CHARS, c.THEME_MAX_CHARS, c.OPINION_MAX_CHARS) == (6, 1500, 2000)
    assert (c.OUTPUT_MAX_CHARS, c.STDERR_MAX_CHARS) == (20000, 4000)
    assert (c.MAX_ROUNDS, c.DEFAULT_ROUNDS, c.MAX_CONCURRENT_PROCS, c.SNAPSHOT_MAX_FILES) == (2, 2, 3, 5000)
    assert (c.BIN_claude, c.BIN_codex, c.BIN_agy) == ("claude", "codex", "agy")
    assert c.CHILD_ENV_EXTRA == "PYTHONUTF8=1"
    assert (c.MARKER_RESERVE, c.TEMPLATE_MAX_CHARS, c.MIN_SUCCESS_R2) == (20, 500, 2)


def test_env_override(monkeypatch):
    monkeypatch.setenv("AI_GOUGI_TIMEOUT_SEC", "3")
    monkeypatch.setenv("AI_GOUGI_CHILD_ENV_EXTRA", "")
    c = get_config()
    assert c.TIMEOUT_SEC == 3
    assert c.CHILD_ENV_EXTRA == ""


def test_t_max_and_derived(monkeypatch):
    assert t_max(1) == 605 and t_max(2) == 1210
    assert keep() == 1980 and w2() == 6000
    assert n_safe() == 3978 and x_lim(7000) == 956
    assert [marker_len(k) for k in (21, 99, 100, 999, 1000, 10000, 18020)] == [12, 12, 13, 13, 14, 15, 15]
    monkeypatch.setenv("AI_GOUGI_TIMEOUT_SEC", "3")
    monkeypatch.setenv("AI_GOUGI_KILL_WAIT_SEC", "2")
    assert t_max(1) == 5 and t_max(2) == 10


def test_order_exclude_taskkill_workdir():
    c = get_config()
    assert c.TASKKILL_FLAGS == "/T /F"
    assert c.PARTICIPANT_ORDER == ("claude", "codex", "agy")
    assert c.SNAPSHOT_EXCLUDE == (".git", "node_modules")
    assert c.WORKDIR == os.path.abspath(os.getcwd()) and os.path.isabs(c.WORKDIR)


def test_marker_at_registered():
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "--strict-markers", "--collect-only", "-q", "-p", "no:cacheprovider",
         __file__ + "::test_defaults_match_table"],
        capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    r = subprocess.run([sys.executable, "-m", "pytest", "--markers"], capture_output=True, text=True)
    assert "@pytest.mark.at" in r.stdout


def test_invalid_env_raises(monkeypatch):
    monkeypatch.setenv("AI_GOUGI_TIMEOUT_SEC", "abc")
    with pytest.raises(ValueError):
        get_config()


def test_t_max_out_of_range_raises():
    with pytest.raises(ValueError):
        t_max(0)
    with pytest.raises(ValueError):
        t_max(3)


def test_t_max_out_of_range_override(monkeypatch):
    monkeypatch.setenv("AI_GOUGI_MAX_ROUNDS", "3")
    assert t_max(3) == 1815


def test_return_cap_H():
    assert return_cap() == 3 * 2 * (20000 + 4000) == 144000
