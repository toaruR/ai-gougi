"""AT-19: stdio 経由(python -m ai_gougi 実 subprocess + stub BIN_*)の isError とスキーマ適合。"""
import importlib.util
import sys
from pathlib import Path

import anyio
import pytest

from ai_gougi.schema import validate_ask_result, validate_deliberate_output

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows 専用")

_spec = importlib.util.spec_from_file_location(
    "smoke_mcp", Path(__file__).parent / "smoke_mcp.py")
smoke = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(smoke)

ASK_TOOLS = {"claude": "ask_claude", "codex": "ask_codex", "agy": "ask_agy"}


def call(tmp_path, modes, calls, extra_env=None):
    params = smoke.stdio_params(str(tmp_path), modes, extra_env)
    return anyio.run(smoke.stdio_session_call, params, calls)


def check_ask(res):
    sc = res.structuredContent
    validate_ask_result(sc)
    assert res.isError is (not sc["ok"])
    return sc


@pytest.mark.at("AT-19")
def test_ask_error_codes_iserror_and_schema(tmp_path):
    # claude=成功 / codex=非0終了 / agy=exit0 で出力空
    modes = {"claude": "echo_stdin", "codex": "exit1", "agy": "sleep"}
    calls = [
        ("ask_claude", {"prompt": "hello"}),
        ("ask_claude", {"prompt": " \n\t"}),
        ("ask_claude", {"prompt": "a" * 7001}),
        ("ask_codex", {"prompt": "hi"}),
        ("ask_agy", {"prompt": "hi"}),
    ]
    got = [check_ask(r) for r in call(tmp_path / "a", modes, calls, {"STUB_SLEEP_SEC": "0"})]
    ok, invalid, too_long, nonzero, empty = got
    assert ok["ok"] is True and ok["stdout"] == "hello" and ok["error_code"] is None
    assert invalid["error_code"] == "INVALID_INPUT"
    assert too_long["error_code"] == "PROMPT_TOO_LONG"
    assert nonzero["error_code"] == "NONZERO_EXIT"
    assert empty["error_code"] == "EMPTY_OUTPUT"

    # CLI_NOT_FOUND
    nf = call(tmp_path / "b", {n: "echo_stdin" for n in ASK_TOOLS}, [("ask_codex", {"prompt": "hi"})],
              {"AI_GOUGI_BIN_codex": str(tmp_path / "nope.cmd")})
    assert check_ask(nf[0])["error_code"] == "CLI_NOT_FOUND"

    # TIMEOUT
    to = call(tmp_path / "c", {"claude": "sleep"}, [("ask_claude", {"prompt": "hi"})],
              {"STUB_SLEEP_SEC": "30", "AI_GOUGI_TIMEOUT_SEC": "1", "AI_GOUGI_KILL_WAIT_SEC": "2"})
    sc = check_ask(to[0])
    assert sc["error_code"] == "TIMEOUT" and sc["timed_out"] is True

    # BUSY: 枠1で同時2呼び出し
    busy = call(tmp_path / "d", {"claude": "sleep"},
                [("ask_claude", {"prompt": "x"}), ("ask_claude", {"prompt": "y"})],
                {"STUB_SLEEP_SEC": "3", "AI_GOUGI_MAX_CONCURRENT_PROCS": "1"})
    codes = sorted(str(check_ask(r)["error_code"]) for r in busy)
    assert "BUSY" in codes
    assert all(r.isError for r in busy)


@pytest.mark.parametrize("modes,status,iserr", [
    ({"claude": "echo_stdin", "codex": "echo_stdin", "agy": "echo_stdin"}, "ok", False),
    ({"claude": "echo_stdin", "codex": "exit1", "agy": "echo_stdin"}, "partial", False),
    ({"claude": "exit1", "codex": "exit1", "agy": "exit1"}, "failed", True),
])
@pytest.mark.at("AT-19")
def test_deliberate_status_iserror(tmp_path, modes, status, iserr):
    res = call(tmp_path, modes, [("deliberate", {"theme": "t"})])[0]
    sc = res.structuredContent
    validate_deliberate_output(sc)
    assert sc["status"] == status
    assert res.isError is iserr


def test_prelaunch_fixed_values(tmp_path):
    modes = {n: "echo_stdin" for n in ASK_TOOLS}
    calls = [
        ("ask_claude", {"prompt": ""}),
        ("ask_claude", {"prompt": "a" * 7001}),
        ("ask_codex", {"prompt": "hi"}),
    ]
    res = call(tmp_path / "a", modes, calls, {"AI_GOUGI_BIN_codex": str(tmp_path / "nope.cmd")})
    busy = call(tmp_path / "b", {"claude": "sleep"},
                [("ask_claude", {"prompt": "x"}), ("ask_claude", {"prompt": "y"})],
                {"STUB_SLEEP_SEC": "3", "AI_GOUGI_MAX_CONCURRENT_PROCS": "1"})
    pre = [check_ask(r) for r in res]
    pre += [s for s in (check_ask(r) for r in busy) if s["error_code"] == "BUSY"]
    assert [s["error_code"] for s in pre] == [
        "INVALID_INPUT", "PROMPT_TOO_LONG", "CLI_NOT_FOUND", "BUSY"]
    for s in pre:
        assert s["stdout"] == ""
        assert s["stdout_total_chars"] == 0
        assert s["workdir_check"] == "skipped"
