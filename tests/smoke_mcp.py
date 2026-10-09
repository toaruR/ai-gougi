"""早期 E2E スモーク: in-process MCP クライアントで stub claude に ask_claude('hello') を1回通す。

使用法: python tests/smoke_mcp.py [--missing-bin] [--stdio] [--tool ask_claude|ask_codex|ask_agy|deliberate] [--rounds N]
--stdio は `python -m ai_gougi` を実 subprocess として stdio_client で起動する。
isError でなければ終了コード0、isError なら1。
"""
import argparse
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

import anyio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402
from mcp.shared.memory import create_connected_server_and_client_session  # noqa: E402

from ai_gougi.mcp_wrap import build_server  # noqa: E402
from ai_gougi.runner import run_cli  # noqa: E402
from ai_gougi.slots import SlotPool  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "make_stubs", Path(__file__).resolve().parent / "stubs" / "make_stubs.py")
_ms = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ms)


def smoke(missing_bin: bool = False, prompt: str = "hello"):
    """ask_claude を1回呼び CallToolResult を返す。環境変数は終了時に復元する。"""
    saved = dict(os.environ)
    try:
        with tempfile.TemporaryDirectory() as td:
            for k, v in _ms.install_stubs(td, "echo_stdin").items():
                os.environ[k] = v
            os.environ["STUB_MODE"] = "echo_stdin"
            if missing_bin:
                os.environ["AI_GOUGI_BIN_claude"] = str(Path(td) / "no_such_claude.cmd")
            pool = SlotPool(3)

            async def cli(participant, p):
                return await run_cli(participant, p, pool=pool)

            server = build_server(cli, None)

            async def main():
                async with create_connected_server_and_client_session(server._mcp_server) as c:
                    return await c.call_tool("ask_claude", {"prompt": prompt})

            return anyio.run(main)
    finally:
        os.environ.clear()
        os.environ.update(saved)


def _load_stub_run():
    sp = importlib.util.spec_from_file_location(
        "stub_run", Path(__file__).resolve().parent / "stubs" / "stub_run.py")
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def stdio_params(td, modes: dict, extra_env: dict | None = None) -> StdioServerParameters:
    """participant->mode の stub shim を td に作り、`python -m ai_gougi` 起動パラメータを返す。"""
    env = dict(os.environ)
    env.update(_load_stub_run().install_deliberate_stubs(td, modes))
    wd = Path(td) / "workdir"
    wd.mkdir(exist_ok=True)
    env["AI_GOUGI_WORKDIR"] = str(wd)
    env.update(extra_env or {})
    return StdioServerParameters(
        command=sys.executable, args=["-m", "ai_gougi"], env=env, cwd=str(ROOT))


async def stdio_session_call(params: StdioServerParameters, calls):
    """1セッションで calls=[(tool, args), ...] を並行実行し CallToolResult のリストを返す。"""
    results = [None] * len(calls)
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as c:
            await c.initialize()

            async def one(i, name, args):
                results[i] = await c.call_tool(name, args)

            async with anyio.create_task_group() as tg:
                for i, (name, args) in enumerate(calls):
                    tg.start_soon(one, i, name, args)
    return results


def smoke_stdio(tool: str = "ask_claude", missing_bin: bool = False, prompt: str = "hello",
                rounds: int | None = None):
    if tool == "deliberate":
        args = {"theme": "t"}
        if rounds is not None:
            args["rounds"] = rounds
        with tempfile.TemporaryDirectory() as td:
            params = stdio_params(td, {n: "echo_stdin" for n in _ms.NAMES})
            return anyio.run(stdio_session_call, params, [(tool, args)])[0]
    part = tool.removeprefix("ask_")
    with tempfile.TemporaryDirectory() as td:
        modes = {n: "echo_stdin" for n in _ms.NAMES}
        extra = {}
        if missing_bin:
            extra[f"AI_GOUGI_BIN_{part}"] = str(Path(td) / f"no_such_{part}.cmd")
        params = stdio_params(td, modes, extra)
        return anyio.run(stdio_session_call, params, [(tool, {"prompt": prompt})])[0]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--missing-bin", action="store_true")
    ap.add_argument("--stdio", action="store_true")
    ap.add_argument("--tool", choices=["ask_claude", "ask_codex", "ask_agy", "deliberate"],
                    default="ask_claude")
    ap.add_argument("--rounds", type=int, default=None)
    a = ap.parse_args(argv)
    if a.stdio:
        res = smoke_stdio(a.tool, a.missing_bin, rounds=a.rounds)
    elif a.tool != "ask_claude":
        ap.error("--tool requires --stdio")
    else:
        res = smoke(a.missing_bin)
    sys.stdout.buffer.write(
        (json.dumps(res.structuredContent, ensure_ascii=False) + "\n").encode("utf-8"))
    return 1 if res.isError else 0


if __name__ == "__main__":
    sys.exit(main())
