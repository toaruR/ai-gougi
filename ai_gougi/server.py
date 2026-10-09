"""実 run_cli / run_deliberate を配線した MCP サーバとエントリポイント(python -m ai_gougi)。"""
from __future__ import annotations

import sys

from .config import get_config
from .deliberate import run_deliberate as _run_deliberate
from .logging_util import is_git_repo, log_nongit_workdir, log_startup_env
from .mcp_wrap import build_server
from .prompts import check_template
from .runner import run_cli


async def _cli(participant: str, prompt: str) -> dict:
    # モジュール属性を呼び出し時に解決(monkeypatch 可能)
    return await run_cli(participant, prompt)


async def _deliberate(theme: str, rounds):
    return await _run_deliberate(theme, rounds)


mcp = build_server(_cli, _deliberate)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    c = get_config()
    check_template(c)  # 超過なら SystemExit(1)
    log_startup_env(c)
    if args and args[0] == "--check-config":
        return 0
    if not is_git_repo(c.WORKDIR):
        log_nongit_workdir(c.WORKDIR)
    mcp.run(transport="stdio")
    return 0
