"""AT-01/AT-02/AT-10: stdio 経由(python -m ai_gougi 実 subprocess + stub BIN_*)の MCP ハッピーパス。"""
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

ALL_ECHO = {"claude": "echo_stdin", "codex": "echo_stdin", "agy": "echo_stdin"}


def call(tmp_path, modes, calls, extra_env=None):
    params = smoke.stdio_params(str(tmp_path), modes, extra_env)
    return anyio.run(smoke.stdio_session_call, params, calls)


@pytest.mark.at("AT-02")
def test_at02_ask_claude_ok_and_empty(tmp_path):
    ok = call(tmp_path / "a", ALL_ECHO, [("ask_claude", {"prompt": "hello"})])[0]
    sc = ok.structuredContent
    validate_ask_result(sc)
    assert ok.isError is False
    assert sc["stdout"] == "hello"

    # 空白のみ出力(sleep stub を 0 秒で終了 → 出力なし)
    empty = call(tmp_path / "b", {"claude": "sleep"}, [("ask_claude", {"prompt": "hi"})],
                 {"STUB_SLEEP_SEC": "0"})[0]
    sc = empty.structuredContent
    validate_ask_result(sc)
    assert empty.isError is True
    assert sc["error_code"] == "EMPTY_OUTPUT"


@pytest.mark.at("AT-10")
def test_at10_rounds_default_and_out_of_range(tmp_path):
    default, over = call(tmp_path, ALL_ECHO, [
        ("deliberate", {"theme": "t"}),
        ("deliberate", {"theme": "t", "rounds": 3}),
    ])
    validate_deliberate_output(default.structuredContent)
    assert default.structuredContent["rounds_requested"] == 2
    validate_deliberate_output(over.structuredContent)
    assert over.isError is True
    assert over.structuredContent["error_code"] == "INVALID_INPUT"


def test_at01_all_ok_via_mcp(tmp_path):
    res = call(tmp_path, ALL_ECHO, [("deliberate", {"theme": "t"})])[0]
    sc = res.structuredContent
    validate_deliberate_output(sc)
    assert res.isError is False
    assert sc["status"] == "ok"
    assert sc["rounds_executed"] == 2
