"""設計書5.4の FastMCP ツール登録と _wrap。run_cli/run_deliberate は注入式。"""
import json
from typing import Annotated, Awaitable, Callable, Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent

from ai_gougi.schema import (
    AskResultAgy,
    AskResultClaude,
    AskResultCodex,
    DeliberateOutput,
)


def _wrap(r: dict) -> CallToolResult:
    if "status" in r:
        failed = r["status"] == "failed"
    elif "ok" in r:
        failed = not r["ok"]
    else:
        raise ValueError("result has neither 'status' nor 'ok'")
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(r, ensure_ascii=False))],
        structuredContent=r,
        isError=failed,
    )


def build_server(
    run_cli_fn: Callable[[str, str], Awaitable[dict]],
    run_deliberate_fn: Optional[Callable[[str, Optional[int]], Awaitable[dict]]] = None,
) -> FastMCP:
    mcp = FastMCP("ai-gougi")

    @mcp.tool(description="Claude Code(plan mode)に質問する。")
    async def ask_claude(prompt: str) -> Annotated[CallToolResult, AskResultClaude]:
        return _wrap(await run_cli_fn("claude", prompt))

    @mcp.tool(description="Codex CLI(read-only)に質問する。")
    async def ask_codex(prompt: str) -> Annotated[CallToolResult, AskResultCodex]:
        return _wrap(await run_cli_fn("codex", prompt))

    @mcp.tool(description="Antigravity CLI(agy)に質問する。")
    async def ask_agy(prompt: str) -> Annotated[CallToolResult, AskResultAgy]:
        return _wrap(await run_cli_fn("agy", prompt))

    @mcp.tool(
        description="全参加者に同一テーマを諮り、独立意見→反論の全結果を返す。整理は呼び出し側。"
    )
    async def deliberate(
        theme: str, rounds: int | None = None
    ) -> Annotated[CallToolResult, DeliberateOutput]:
        if run_deliberate_fn is None:
            raise NotImplementedError("run_deliberate is not implemented")
        return _wrap(await run_deliberate_fn(theme, rounds))

    return mcp
