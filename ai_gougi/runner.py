"""run_cli の起動前段(設計書4,5.3): 検証→枠予約→BIN解決→argv構築。subprocess 起動は後続タスク。

エラー優先順位: INVALID_INPUT -> PROMPT_TOO_LONG -> BUSY -> CLI_NOT_FOUND -> CMDLINE_TOO_LONG
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from typing import Optional, Union

from .cmdline import apply_newline, check_cmdline_len
from .config import Config, get_config
from .schema import AskResult, make_ask_result, make_prelaunch_error
from .slots import SlotPool

POOL = SlotPool()

_PARTICIPANTS = ("claude", "codex", "agy")


@dataclass
class LaunchPlan:
    participant: str
    argv: list
    stdin_text: Optional[str]  # stdin 経路のプロンプト。agy は None
    stdin_devnull: bool  # agy のみ True
    slot_held: bool  # この呼出しが枠を確保している(後続の起動処理が解放する)
    cfg: Config = field(repr=False, default=None)


def _argv_base(participant: str, exe: str, prompt: str) -> tuple[list, Optional[str], bool]:
    if participant == "claude":
        return [exe, "-p", "--permission-mode", "plan"], prompt, False
    if participant == "codex":
        return [exe, "exec", "--sandbox", "read-only", "--skip-git-repo-check", "-"], prompt, False
    ext = os.path.splitext(exe)[1]
    return [exe, "-p", apply_newline(prompt, ext)], None, True


def prelaunch(
    participant: str,
    prompt: str,
    *,
    pool: SlotPool | None = None,
    reserved: bool = False,
    cfg: Config | None = None,
) -> Union[AskResult, LaunchPlan]:
    """起動前検証。エラーなら AskResult(枠は呼出し前の状態に戻す)、成功なら LaunchPlan。

    reserved=True は deliberate が枠確保済みの場合で、BUSY 判定・予約・解放を行わない。
    """
    c = cfg if cfg is not None else get_config()
    pool = pool if pool is not None else POOL

    if participant not in _PARTICIPANTS:
        return make_prelaunch_error(
            participant, "INVALID_INPUT", f"unknown participant: {participant!r}"
        )
    if not isinstance(prompt, str) or not prompt.strip():
        return make_prelaunch_error(participant, "INVALID_INPUT", "prompt must not be blank")
    if len(prompt) > c.PROMPT_MAX_CHARS:
        return make_prelaunch_error(
            participant,
            "PROMPT_TOO_LONG",
            f"prompt length {len(prompt)} > {c.PROMPT_MAX_CHARS}",
        )

    held = False
    if not reserved:
        if not pool.try_reserve(1):
            return make_prelaunch_error(participant, "BUSY", "all process slots are busy")
        held = True

    def fail(code: str, msg: str) -> AskResult:
        if held:
            pool.release(1)
        return make_prelaunch_error(participant, code, msg)

    bin_name = getattr(c, f"BIN_{participant}")
    found = shutil.which(bin_name)
    if not found:
        return fail("CLI_NOT_FOUND", f"BIN_{participant} not found: {bin_name}")
    exe = os.path.abspath(found)

    argv, stdin_text, devnull = _argv_base(participant, exe, prompt)
    if participant == "agy":
        try:
            check_cmdline_len(exe, prompt, c)
        except ValueError as e:
            return fail("CMDLINE_TOO_LONG", str(e))
    return LaunchPlan(participant, argv, stdin_text, devnull, held, c)


async def run_cli(
    participant: str,
    prompt: str,
    *,
    pool: SlotPool | None = None,
    reserved: bool = False,
) -> AskResult:
    """起動前段のみ(実行段は後続タスク)。成功時は枠を解放して NotImplementedError。"""
    plan = prelaunch(participant, prompt, pool=pool, reserved=reserved)
    if not isinstance(plan, LaunchPlan):
        return plan
    if plan.slot_held:
        (pool if pool is not None else POOL).release(1)
    raise NotImplementedError("execution stage is not implemented yet")
