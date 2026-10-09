import importlib.util
import subprocess
import sys
from pathlib import Path

from ai_gougi.schema import validate_ask_result

_P = Path(__file__).parent / "smoke_mcp.py"
_spec = importlib.util.spec_from_file_location("smoke_mcp", _P)
smoke_mcp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(smoke_mcp)


def test_smoke_ask_claude_in_process():
    res = smoke_mcp.smoke()
    assert res.isError is False
    sc = res.structuredContent
    assert sc["participant"] == "claude"
    assert sc["stdout"] == "hello"
    validate_ask_result(sc)


def test_smoke_missing_bin_is_error():
    res = smoke_mcp.smoke(missing_bin=True)
    assert res.isError is True
    assert res.structuredContent["error_code"] == "CLI_NOT_FOUND"


def test_smoke_cli_exit_codes():
    ok = subprocess.run([sys.executable, str(_P)], capture_output=True)
    bad = subprocess.run([sys.executable, str(_P), "--missing-bin"], capture_output=True)
    assert ok.returncode == 0
    assert bad.returncode == 1
