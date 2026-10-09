import json

import anyio
import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from ai_gougi.mcp_wrap import _wrap, build_server
from ai_gougi.schema import make_ask_result


def _run(coro_fn):
    return anyio.run(coro_fn)


def _with_client(server, fn):
    async def main():
        async with create_connected_server_and_client_session(server._mcp_server) as c:
            return await fn(c)

    return _run(main)


def _fake_cli(result_for=None, calls=None):
    async def run_cli(participant, prompt):
        if calls is not None:
            calls.append((participant, prompt))
        if result_for:
            return result_for(participant, prompt)
        return make_ask_result(participant, ok=True, exit_code=0, stdout="ok")

    return run_cli


def _delib(status):
    return {
        "status": status, "error_code": None, "error_message": None,
        "rounds_requested": 1, "rounds_executed": 1, "skipped_reason": None,
        "elapsed_ms": 1, "rounds": [],
    }


def test_tools_list_four_with_schemas():
    server = build_server(_fake_cli(), None)

    async def fn(c):
        return (await c.list_tools()).tools

    tools = {t.name: t for t in _with_client(server, fn)}
    assert set(tools) == {"ask_claude", "ask_codex", "ask_agy", "deliberate"}
    for t in tools.values():
        assert t.outputSchema is not None
    for n in ("ask_claude", "ask_codex", "ask_agy"):
        s = tools[n].inputSchema
        assert set(s["properties"]) == {"prompt"}
        assert s["properties"]["prompt"]["type"] == "string"
        assert s["required"] == ["prompt"]
    d = tools["deliberate"].inputSchema
    assert d["required"] == ["theme"]
    assert "integer" in json.dumps(d["properties"]["rounds"])


def test_iserror_and_structured_content():
    fake = make_ask_result(
        "claude", ok=False, exit_code=1, stdout="日本語の出力", error_code="NONZERO_EXIT",
        error_message="失敗",
    )
    server = build_server(_fake_cli(lambda p, q: fake), None)

    async def fn(c):
        return await c.call_tool("ask_claude", {"prompt": "hi"})

    res = _with_client(server, fn)
    assert res.isError is True
    assert res.structuredContent == fake
    assert json.loads(res.content[0].text) == fake
    assert "日本語の出力" in res.content[0].text


def test_ok_ask_not_error():
    server = build_server(_fake_cli(), None)

    async def fn(c):
        return [await c.call_tool(n, {"prompt": "x"}) for n in ("ask_claude", "ask_codex", "ask_agy")]

    for res in _with_client(server, fn):
        assert res.isError is False


@pytest.mark.parametrize("status,err", [("ok", False), ("partial", False), ("failed", True)])
def test_deliberate_status_iserror(status, err):
    async def rd(theme, rounds):
        return _delib(status)

    server = build_server(_fake_cli(), rd)

    async def fn(c):
        return await c.call_tool("deliberate", {"theme": "t"})

    assert _with_client(server, fn).isError is err


def test_participant_fixed_per_tool():
    server = build_server(_fake_cli(), None)

    async def fn(c):
        return (await c.list_tools()).tools

    tools = {t.name: t for t in _with_client(server, fn)}

    def has_const(name, value):
        txt = json.dumps(tools[name].outputSchema)
        return json.dumps(value) in txt

    assert has_const("ask_codex", "codex") and not has_const("ask_codex", "agy")
    assert has_const("ask_agy", "agy") and not has_const("ask_agy", "codex")
    assert has_const("ask_claude", "claude")


def test_rounds_none_passthrough():
    seen = []

    async def rd(theme, rounds):
        seen.append((theme, rounds))
        return _delib("ok")

    server = build_server(_fake_cli(), rd)

    async def fn(c):
        await c.call_tool("deliberate", {"theme": "t"})
        await c.call_tool("deliberate", {"theme": "u", "rounds": 2})

    _with_client(server, fn)
    assert seen == [("t", None), ("u", 2)]


def test_deliberate_without_runner_errors():
    server = build_server(_fake_cli(), None)

    async def fn(c):
        return await c.call_tool("deliberate", {"theme": "t"})

    res = _with_client(server, fn)
    assert res.isError is True
    assert "NotImplementedError" in res.content[0].text or "not implemented" in res.content[0].text


def test_wrap_rejects_malformed_result():
    with pytest.raises(ValueError):
        _wrap({})
    assert _wrap({"ok": True}).isError is False
