"""run_cli の起動前段(設計書4,5.3): 検証→枠予約→BIN解決→argv構築。subprocess 起動は後続タスク。

エラー優先順位: INVALID_INPUT -> PROMPT_TOO_LONG -> BUSY -> CLI_NOT_FOUND -> CMDLINE_TOO_LONG
"""
from __future__ import annotations

import asyncio
import os
import shutil
import time
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


async def _feed_stdin(proc, data: Optional[bytes]) -> None:
    if proc.stdin is None or data is None:
        return
    try:
        proc.stdin.write(data)
        await proc.stdin.drain()
        proc.stdin.close()  # EOF
    except OSError:
        pass


async def _execute(plan: LaunchPlan) -> AskResult:
    """実行段A: 起動・stdin/EOF/DEVNULL・ok 判定。タイムアウト/切詰め/snapshot は後続タスク。"""
    c = plan.cfg
    p = plan.participant
    t0 = time.monotonic()

    def ms() -> int:
        return int((time.monotonic() - t0) * 1000)

    try:
        proc = await asyncio.create_subprocess_exec(
            *plan.argv,
            cwd=c.WORKDIR,
            stdin=asyncio.subprocess.DEVNULL if plan.stdin_devnull else asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except (OSError, ValueError) as e:
        return make_ask_result(
            p, ok=False, exit_code=None, duration_ms=ms(), workdir_check="skipped",
            error_code="SPAWN_FAILED", error_message=f"{type(e).__name__}: {e}",
        )

    data = plan.stdin_text.encode(c.ENCODING) if plan.stdin_text is not None else None
    feeder = asyncio.ensure_future(_feed_stdin(proc, data))
    out_b, err_b = await asyncio.gather(proc.stdout.read(), proc.stderr.read())
    await proc.wait()
    await feeder

    stdout = out_b.decode(c.ENCODING, errors="replace")
    stderr = err_b.decode(c.ENCODING, errors="replace")
    code = proc.returncode
    ok = code == 0 and bool(stdout.strip())
    error_code = error_message = None
    if code != 0:
        error_code, error_message = "NONZERO_EXIT", f"exit code {code}"
    elif not ok:
        error_code, error_message = "EMPTY_OUTPUT", "stdout is empty"
    return make_ask_result(
        p, ok=ok, exit_code=code, stdout=stdout, stderr=stderr,
        duration_ms=ms(), workdir_check="skipped",
        error_code=error_code, error_message=error_message,
    )


async def run_cli(
    participant: str,
    prompt: str,
    *,
    pool: SlotPool | None = None,
    reserved: bool = False,
) -> AskResult:
    """起動前段 + 実行段A。枠は全経路で解放する。"""
    plan = prelaunch(participant, prompt, pool=pool, reserved=reserved)
    if not isinstance(plan, LaunchPlan):
        return plan
    try:
        return await _execute(plan)
    finally:
        if plan.slot_held:
            (pool if pool is not None else POOL).release(1)


