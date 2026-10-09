"""早期 E2E スモーク: in-process MCP クライアントで stub claude に ask_claude('hello') を1回通す。

使用法: python tests/smoke_mcp.py [--missing-bin]
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--missing-bin", action="store_true")
    a = ap.parse_args(argv)
    res = smoke(a.missing_bin)
    sys.stdout.buffer.write(
        (json.dumps(res.structuredContent, ensure_ascii=False) + "\n").encode("utf-8"))
    return 1 if res.isError else 0


if __name__ == "__main__":
    sys.exit(main())
