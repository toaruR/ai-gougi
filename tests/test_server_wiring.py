import os
import subprocess
import sys

import anyio
from mcp.shared.memory import create_connected_server_and_client_session

import ai_gougi.server as server
from ai_gougi.schema import make_ask_result

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _py(*args, env_extra=None):
    env = dict(os.environ, **(env_extra or {}))
    return subprocess.run(
        [sys.executable, *args], cwd=ROOT, env=env, capture_output=True, timeout=60
    )


def _client(fn):
    async def main():
        async with create_connected_server_and_client_session(server.mcp._mcp_server) as c:
            return await fn(c)

    return anyio.run(main)


def test_import_and_tools_list():
    assert _py("-c", "import ai_gougi.server").returncode == 0

    async def fn(c):
        return (await c.list_tools()).tools

    names = {t.name for t in _client(fn)}
    assert {"ask_claude", "ask_codex", "ask_agy", "deliberate"} <= names


def test_template_overlimit_exits_1():
    assert _py("-m", "ai_gougi", "--check-config").returncode == 0
    r = _py("-m", "ai_gougi", "--check-config", env_extra={"AI_GOUGI_TEMPLATE_MAX_CHARS": "1"})
    assert r.returncode == 1


def test_ask_claude_calls_real_run_cli(monkeypatch):
    calls = []

    async def fake(participant, prompt, **kw):
        calls.append((participant, prompt))
        return make_ask_result(participant, ok=True, exit_code=0, stdout="x")

    monkeypatch.setattr(server, "run_cli", fake)

    async def fn(c):
        return await c.call_tool("ask_claude", {"prompt": "hi"})

    res = _client(fn)
    assert calls == [("claude", "hi")]
    assert not res.isError


def test_startup_log_stderr_only():
    r = _py("-m", "ai_gougi", "--check-config")
    assert r.returncode == 0
    assert r.stdout == b""
    assert b"startup_env" in r.stderr
